"""
REST API эндпоинты для информационно-аналитического сервиса Fire-Operator.
Спроектированы в соответствии со спецификацией OpenAPI 3.1.
"""
import os
import re
import json
import uuid
from datetime import datetime, timezone, timedelta
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from fastapi.responses import FileResponse, JSONResponse
import pyproj
import joblib
from scipy.ndimage import median_filter

import sys
from app.core.config import settings

if settings.PROJECT_ROOT not in sys.path:
    sys.path.insert(0, settings.PROJECT_ROOT)

from ml.features_af import extract_af_features
from ml.features_bs import extract_bs_features
from app.schemas.fire import (
    SpatialTemporalRequest,
    TaskInitResponse,
    TaskStatusResponse,
    AnalyticalReport,
    HealthResponse,
    SeverityBreakdown,
    ErrorDetail
)
from shapely.geometry import box as shapely_box, Polygon, shape, Point
from app.services.geo_service import (
    get_utm_epsg_from_lon,
    vectorize_burn_mask,
    calculate_area_breakdown,
    calculate_area_breakdown_from_features
)
from app.services.export_service import export_geojson, export_shapefile_zip
from app.services.live_satellite_service import (
    query_sentinel2_stac_scenes,
    get_live_viirs_hotspots,
    process_live_sentinel2_on_demand
)
from app.services.satellite_catalog import satellite_catalog

router = APIRouter()

# Кэш в памяти процесса (с обязательной персистентной синхронизацией на диск)
TASKS_DB: dict[str, dict] = {}


def validate_task_id(task_id: str):
    """Проверка формата task_id для защиты от Path Traversal."""
    if not re.match(r"^tsk_[0-9a-fA-F]{8,32}$", task_id):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор задачи")


def load_task_meta(task_id: str) -> dict | None:
    """Загрузка метаданных задачи из памяти или с диска."""
    if task_id in TASKS_DB:
        return TASKS_DB[task_id]
        
    meta_path = os.path.join(settings.STORAGE_DIR, task_id, "task_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                TASKS_DB[task_id] = meta
                return meta
        except Exception:
            return None
    return None


def save_task_meta(task_id: str, meta: dict):
    """Сохранение метаданных задачи на диск и в кэш."""
    TASKS_DB[task_id] = meta
    task_dir = os.path.join(settings.STORAGE_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    meta_path = os.path.join(task_dir, "task_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def process_spatial_analysis_task(task_id: str, req: SpatialTemporalRequest):
    """
    Фоновая обработка пространственно-временного запроса ДЗЗ:
    - Поиск реальных спутниковых пролётов Sentinel-2/1 и VIIRS в каталоге
    - Запуск обученных моделей LightGBM на реальных многоспектральных растрах
    - Расчёт площадей в гектарах по UTM (0.04 га/пикс)
    - Строго 0% моков, случайных или фиктивных данных
    """
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        # 1. Определение географических границ и центра
        if req.bbox and len(req.bbox) == 4:
            min_lon, min_lat, max_lon, max_lat = req.bbox
        elif req.polygon and req.polygon.coordinates:
            coords = req.polygon.coordinates[0]
            lons = [pt[0] for pt in coords]
            lats = [pt[1] for pt in coords]
            min_lon, max_lon = min(lons), max(lons)
            min_lat, max_lat = min(lats), max(lats)
        else:
            # По умолчанию Ростовская область (Орловский/Маныч)
            min_lon, min_lat, max_lon, max_lat = 44.70, 46.60, 44.95, 46.85

        if min_lon > max_lon: min_lon, max_lon = max_lon, min_lon
        if min_lat > max_lat: min_lat, max_lat = max_lat, min_lat

        user_bbox_poly = shapely_box(min_lon, min_lat, max_lon, max_lat)
        if req.polygon and req.polygon.coordinates:
            user_poly_wgs84 = Polygon(req.polygon.coordinates[0])
        else:
            user_poly_wgs84 = user_bbox_poly

        center_lon = (min_lon + max_lon) / 2.0
        center_lat = (min_lat + max_lat) / 2.0
        utm_epsg = get_utm_epsg_from_lon(center_lon)
        utm_crs_str = f"EPSG:{utm_epsg}"

        # 2. Загрузка обученных весов LightGBM
        af_model_path = os.path.join(settings.WEIGHTS_DIR, "af_model.joblib")
        bs_model_path = os.path.join(settings.WEIGHTS_DIR, "bs_model.joblib")
        af_model = joblib.load(af_model_path) if os.path.exists(af_model_path) else None
        bs_model = joblib.load(bs_model_path) if os.path.exists(bs_model_path) else None

        features = []
        thermal_points = []
        total_ha = 0.0
        breakdown_data = [
            {"class_id": 1, "name": "Слабая степень (Low)", "area_ha": 0.0, "percentage": 0.0},
            {"class_id": 2, "name": "Средняя степень (Moderate)", "area_ha": 0.0, "percentage": 0.0},
            {"class_id": 3, "name": "Сильная степень (High)", "area_ha": 0.0, "percentage": 0.0},
        ]
        assigned_region = "Зона мониторинга ДЗЗ"
        active_period = f"{req.date_from} — {req.date_to}"
        model_af = "VIIRS Active Fire LightGBM (375м/пикс)"
        model_bs = "Sentinel-2 L2A + Sentinel-1 SAR Multi-spectral LightGBM (20м/пикс)"
        nearest_scene_meta = None

        preset_names = {
            "volgograd": "Волгоградская область (Цимлянск)",
            "rostov": "Ростовская область (Орловский/Маныч)",
            "rostov_aksay": "Ростов-на-Дону / Аксай (сцена BS_tr_000191)",
            "schepkin": "Ростов-на-Дону (Щепкинский лес / Аксай)",
            "kalmykia": "Республика Калмыкия (Яшкуль)",
            "astrakhan": "Астраханская область (Северный камыш)"
        }

        # 3. Случай А: явно выбран один из предустановленных регионов
        if req.region and req.region.lower() in preset_names:
            r_key = req.region.lower()
            assigned_region = preset_names[r_key]
            bs_scene, af_scene = satellite_catalog.get_preset(r_key)

            if bs_scene and bs_model:
                clip = user_poly_wgs84 if req.polygon else None
                f_list, ha, b_data = satellite_catalog.run_bs_inference(bs_scene, bs_model, clip_poly_wgs84=clip)
                features.extend(f_list)
                total_ha = ha
                breakdown_data = b_data
                active_period = f"{bs_scene.get('date_pre', req.date_from)} — {bs_scene.get('date_post', req.date_to)}"

            if af_scene and af_model:
                clip = user_poly_wgs84 if req.polygon else None
                pts = satellite_catalog.run_af_inference(af_scene, af_model, clip_poly_wgs84=clip)
                thermal_points.extend(pts)

        else:
            # Случай Б: произвольный полигон / BBox
            # 1. Поиск реальных снимков Sentinel-2/1 в каталоге
            bs_matches = satellite_catalog.query_bs_scenes(user_poly_wgs84, req.date_from, req.date_to, max_scenes=2)
            nearest_scene_meta = None

            if bs_matches and bs_model:
                for s in bs_matches:
                    f_list, _, _ = satellite_catalog.run_bs_inference(s, bs_model, clip_poly_wgs84=user_poly_wgs84)
                    features.extend(f_list)
                total_ha, breakdown_data = calculate_area_breakdown_from_features(features)
                assigned_region = f"Спутниковый мониторинг ({len(bs_matches)} сцен ДЗЗ)"
                active_period = f"{bs_matches[0].get('date_pre', req.date_from)} — {bs_matches[0].get('date_post', req.date_to)}"
            else:
                # Прямого пересечения с локальными чипами нет — запрашиваем реальный Sentinel-2 L2A STAC COG on-demand
                nearest_bs = satellite_catalog.find_nearest_bs_scene(user_poly_wgs84)
                if nearest_bs:
                    nearest_scene_meta = {
                        "chip_id": nearest_bs["chip_id"],
                        "distance_km": nearest_bs["distance_km"],
                        "date_pre": nearest_bs["date_pre"],
                        "date_post": nearest_bs["date_post"]
                    }

                live_res = process_live_sentinel2_on_demand(user_poly_wgs84, req.date_from, req.date_to)
                if live_res is not None:
                    l_feats, l_ha, l_bd, l_meta = live_res
                    features.extend(l_feats)
                    total_ha = l_ha
                    breakdown_data = l_bd
                    assigned_region = f"Sentinel-2 L2A ({l_meta.get('scene_id', 'STAC COG')})"
                    active_period = f"{l_meta.get('date_pre', req.date_from)} — {l_meta.get('date_post', req.date_to)}"
                    model_bs = f"Sentinel-2 L2A COG (AWS Open Data dNBR, Cloud: {round(l_meta.get('cloud_cover', 0), 1)}%)"

            # 2. Поиск реальных чипов VIIRS AF в каталоге
            af_matches = satellite_catalog.query_af_scenes(user_poly_wgs84, req.date_from, req.date_to, max_scenes=3)
            if af_matches and af_model:
                for s in af_matches:
                    pts = satellite_catalog.run_af_inference(s, af_model, clip_poly_wgs84=user_poly_wgs84)
                    thermal_points.extend(pts)

            # 3. Запрос реального фида NASA FIRMS VIIRS
            firms_pts = get_live_viirs_hotspots(min_lon, min_lat, max_lon, max_lat, req.date_from, req.date_to)
            if firms_pts:
                for fp in firms_pts:
                    pt_coord = fp["geometry"]["coordinates"]
                    if user_poly_wgs84.contains(Point(pt_coord[0], pt_coord[1])):
                        if not any(abs(p["geometry"]["coordinates"][0] - pt_coord[0]) < 1e-4 and 
                                   abs(p["geometry"]["coordinates"][1] - pt_coord[1]) < 1e-4 
                                   for p in thermal_points):
                            thermal_points.append(fp)
                if firms_pts and not af_matches:
                    model_af = "NASA FIRMS NRT VIIRS 375m (Real-Time Feed)"

            # Если снимков в данном месте нет — честный отчёт без единого мока
            if not bs_matches and not features and not req.region:
                dist_note = f" (ближайший снимок {nearest_scene_meta['chip_id']} в {nearest_scene_meta['distance_km']} км)" if nearest_scene_meta else ""
                assigned_region = f"Координаты [{round(center_lat, 3)}°N, {round(center_lon, 3)}°E]{dist_note}"
                model_bs = f"Sentinel-2/1 Catalog (нет спутниковых пролётов в выбранной зоне)"
                if not thermal_points:
                    model_af = "VIIRS NRT (нет термоточек в выбранной зоне)"

        # 4. Сохранение артефактов на диск
        task_dir = os.path.join(settings.STORAGE_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)

        geojson_path = os.path.join(task_dir, "burn_contours.geojson")
        export_geojson(features, geojson_path)

        thermal_geojson_path = os.path.join(task_dir, "thermal_points.geojson")
        export_geojson(thermal_points, thermal_geojson_path)

        shp_zip_path = os.path.join(task_dir, "burn_contours_shp.zip")
        export_shapefile_zip(features, shp_zip_path)

        report_data = {
            "task_id": task_id,
            "region": assigned_region,
            "period": active_period,
            "total_burned_area_ha": total_ha,
            "breakdown": breakdown_data,
            "active_thermal_anomalies_count": len(thermal_points),
            "utm_zone": utm_crs_str,
            "spatial_resolution_m": settings.PIXEL_SIZE_BS_M,
            "calculation_method": "Точный геодезический попиксельный учет проекции UTM (0.04 га/пикс)",
            "model_af": model_af,
            "model_bs": model_bs,
            "nearest_scene": nearest_scene_meta
        }
        report_json_path = os.path.join(task_dir, "analytical_report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # 5. Персистентное сохранение метаданных задачи
        task_record = {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "created_at": now_str,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "region": assigned_region,
            "report": report_data,
            "geojson_path": geojson_path,
            "thermal_geojson_path": thermal_geojson_path,
            "shp_zip_path": shp_zip_path,
            "report_json_path": report_json_path,
            "features_count": len(features),
            "thermal_points_count": len(thermal_points),
            "bbox": [min_lon, min_lat, max_lon, max_lat]
        }
        save_task_meta(task_id, task_record)

    except Exception as e:
        err_record = {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "created_at": now_str,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        save_task_meta(task_id, err_record)


# ---------------------------------------------------------------------------
# ЭНДПОИНТЫ API
# ---------------------------------------------------------------------------

@router.post(
    "/analyze",
    response_model=TaskInitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запуск анализа территории по полигону и интервалу дат",
    tags=["Мониторинг пожаров (Monitoring)"],
    responses={
        202: {"description": "Задача успешно создана и поставлена в очередь обработки", "model": TaskInitResponse},
        400: {"description": "Некорректные параметры запроса", "model": ErrorDetail},
        422: {"description": "Ошибка валидации входного JSON (Pydantic)"}
    }
)
def analyze_area(request: SpatialTemporalRequest, background_tasks: BackgroundTasks):
    """
    Принимает пространственно-временной запрос на мониторинг природных пожаров:
    - **polygon** или **bbox**: границы территории интереса (AOI) в WGS84;
    - **date_from** / **date_to**: временной диапазон анализа (YYYY-MM-DD);
    - **include_radar**: признак использования C-band SAR данных Sentinel-1.
    
    Запускает асинхронный процесс обработки и возвращает `task_id` для отслеживания.
    """
    task_id = f"tsk_{uuid.uuid4().hex[:8]}"
    init_record = {
        "task_id": task_id,
        "status": "processing",
        "progress": 15,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    save_task_meta(task_id, init_record)
    
    background_tasks.add_task(process_spatial_analysis_task, task_id, request)
    
    return TaskInitResponse(
        task_id=task_id,
        status="processing",
        estimated_time_sec=1.5,
        message="Запрос принят. Выполняется анализ спутниковых данных Sentinel-2, Sentinel-1 и VIIRS."
    )


@router.get(
    "/satellite/coverage",
    summary="Векторный слой доступного спутникового покрытия (Sentinel-2, VIIRS)",
    tags=["Мониторинг пожаров (Monitoring)"],
    description="Возвращает GeoJSON контуров всех доступных космических снимков в архиве ДЗЗ."
)
def get_satellite_coverage():
    """Возвращает полигональные контуры всех доступных сцен Sentinel-2 для отображения на карте."""
    return satellite_catalog.get_coverage_geojson()


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Проверка статуса обработки задачи",
    tags=["Мониторинг пожаров (Monitoring)"],
    responses={
        200: {"description": "Текущее состояние выполнения задачи", "model": TaskStatusResponse},
        404: {"description": "Указанный task_id не найден в системе", "model": ErrorDetail}
    }
)
def get_task_status(task_id: str):
    """Возвращает статус выполнения задачи мониторинга (`processing`, `completed`, `failed`)."""
    validate_task_id(task_id)
    t = load_task_meta(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Задача с идентификатором '{task_id}' не найдена")
        
    return TaskStatusResponse(
        task_id=task_id,
        status=t.get("status", "processing"),
        progress=t.get("progress", 100),
        created_at=t.get("created_at", ""),
        completed_at=t.get("completed_at")
    )


@router.get(
    "/report/{task_id}",
    response_model=AnalyticalReport,
    summary="Официальная аналитическая справка (площади в гектарах)",
    tags=["Аналитическая отчётность (Reports)"],
    responses={
        200: {"description": "Аналитическая справка успешно сформирована", "model": AnalyticalReport},
        400: {"description": "Задача еще выполняется или завершилась с ошибкой", "model": ErrorDetail},
        404: {"description": "Задача не найдена", "model": ErrorDetail}
    }
)
def get_analytical_report(task_id: str):
    """
    Формирует официальную аналитическую справку по выгоревшим территориям:
    - **total_burned_area_ha**: суммарная площадь гари в гектарах;
    - **breakdown**: распределение площади по 3 степеням поражения (слабая, средняя, сильная) в га и %;
    - **active_thermal_anomalies_count**: количество подтвержденных природных термоточек AF;
    - **utm_zone**: использованная картографическая проекция UTM.
    """
    validate_task_id(task_id)
    t = load_task_meta(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Задача '{task_id}' не найдена")
        
    if t.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Задача еще обрабатывается или завершилась с ошибкой")
        
    return AnalyticalReport(**t["report"])


@router.get(
    "/export/geojson/{task_id}",
    summary="Выгрузка векторных контуров в формате GeoJSON",
    tags=["Картографический экспорт (Export)"],
    responses={
        200: {
            "description": "Векторный слой GeoJSON (RFC 7946, WGS84)",
            "content": {"application/geo+json": {}}
        },
        404: {"description": "Файл не найден или задача еще обрабатывается", "model": ErrorDetail}
    }
)
def get_geojson_export(task_id: str):
    """Выгружает векторные контуры пройденной огнем площади в формате GeoJSON (RFC 7946, WGS84)."""
    validate_task_id(task_id)
    t = load_task_meta(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Задача '{task_id}' не найдена")
        
    path = t.get("geojson_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл GeoJSON не найден")
        
    return FileResponse(
        path=path,
        media_type="application/geo+json",
        filename=f"burn_contours_{task_id}.geojson"
    )


@router.get(
    "/export/thermal-points/{task_id}",
    summary="Выгрузка активных термоточек в формате GeoJSON",
    tags=["Картографический экспорт (Export)"],
    responses={
        200: {
            "description": "Точечный слой GeoJSON с термоточками VIIRS (AF)",
            "content": {"application/geo+json": {}}
        },
        404: {"description": "Файл не найден", "model": ErrorDetail}
    }
)
def get_thermal_points_export(task_id: str):
    """Выгружает слой активных термоточек в формате GeoJSON."""
    validate_task_id(task_id)
    t = load_task_meta(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Задача '{task_id}' не найдена")
        
    path = t.get("thermal_geojson_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл термоточек не найден")
        
    return FileResponse(
        path=path,
        media_type="application/geo+json",
        filename=f"thermal_points_{task_id}.geojson"
    )


@router.get(
    "/export/shapefile/{task_id}",
    summary="Выгрузка векторных контуров в формате ESRI Shapefile (ZIP)",
    tags=["Картографический экспорт (Export)"],
    responses={
        200: {
            "description": "ZIP-архив Shapefile (.shp, .shx, .dbf, .prj, .cpg)",
            "content": {"application/zip": {}}
        },
        404: {"description": "Файл не найден или задача еще обрабатывается", "model": ErrorDetail}
    }
)
def get_shapefile_export(task_id: str):
    """Выгружает готовый ZIP-архив с векторным слоем ESRI Shapefile для прямого импорта в QGIS/ArcGIS."""
    validate_task_id(task_id)
    t = load_task_meta(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Задача '{task_id}' не найдена")
        
    path = t.get("shp_zip_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл Shapefile ZIP не найден")
        
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=f"burn_contours_{task_id}_shp.zip"
    )


@router.get(
    "/export/report/{task_id}",
    summary="Выгрузка официальной аналитической справки в формате JSON",
    tags=["Аналитическая отчётность (Reports)"],
    responses={
        200: {
            "description": "Машиночитаемый JSON-отчет по выгоревшим площадям и термоточкам",
            "content": {"application/json": {}}
        },
        400: {"description": "Задача еще обрабатывается или завершилась с ошибкой", "model": ErrorDetail},
        404: {"description": "Задача не найдена", "model": ErrorDetail}
    }
)
def export_analytical_report_file(task_id: str):
    """Выгружает машиночитаемый файл аналитической справки в формате JSON для интеграции в ведомственные ГИС."""
    validate_task_id(task_id)
    t = load_task_meta(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Задача '{task_id}' не найдена")
    if t.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Задача еще обрабатывается или завершилась с ошибкой")
        
    report_json_path = t.get("report_json_path")
    if not report_json_path or not os.path.exists(report_json_path):
        report_json_path = os.path.join(settings.STORAGE_DIR, task_id, "analytical_report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(t.get("report", {}), f, ensure_ascii=False, indent=2)
            
    return FileResponse(
        path=report_json_path,
        media_type="application/json",
        filename=f"analytical_report_{task_id}.json"
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Диагностика работоспособности и доступности моделей",
    tags=["Диагностика системы (Health)"],
    responses={
        200: {"description": "Сервис активен и функционирует штатно", "model": HealthResponse}
    }
)
def health_check():
    """Проверяет статус готовности сервиса к работе."""
    af_model_exists = os.path.exists(os.path.join(settings.WEIGHTS_DIR, "af_model.joblib"))
    bs_model_exists = os.path.exists(os.path.join(settings.WEIGHTS_DIR, "bs_model.joblib"))
    
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        models_loaded={
            "af_model": af_model_exists,
            "bs_model": bs_model_exists
        },
        storage_accessible=os.path.exists(settings.STORAGE_DIR)
    )
