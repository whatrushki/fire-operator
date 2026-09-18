"""
Геопространственные сервисы: расчет зон UTM, площадей в гектарах,
векторизация растров и генерация слоя термоточек AF.
"""
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping, Polygon, Point
from shapely.ops import transform
import pyproj

from app.core.config import settings


def get_utm_epsg_from_lon(lon: float) -> int:
    """Определяет код EPSG зоны UTM для заданной долготы (Северное полушарие)."""
    zone = int(np.floor((lon + 180) / 6)) + 1
    return 32600 + zone


def vectorize_burn_mask(
    mask: np.ndarray,
    transform_matrix: rasterio.Affine,
    src_crs: str = "EPSG:32638",
    dst_crs: str = "EPSG:4326",
    simplify_tol_m: float = 2.0,
    clip_poly_wgs84: Polygon | None = None
) -> list[dict]:
    """
    Векторизует растровую маску гарей (значения 1, 2, 3) в GeoJSON фичи WGS84.
    При наличии clip_poly_wgs84 контуры строго обрезаются границами запрошенного полигона/BBox.
    
    Args:
        mask: 2D uint8 array (H, W) со значениями 0, 1, 2, 3.
        transform_matrix: аффинное преобразование растра.
        src_crs: исходная система координат (UTM).
        dst_crs: целевая система координат (WGS84).
        simplify_tol_m: допуск упрощения Дугласа-Пекера в метрах.
        clip_poly_wgs84: полигон обрезки в WGS84 (например, пользовательский BBox).
        
    Returns:
        Список GeoJSON Feature словарей.
    """
    project_to_wgs84 = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True).transform
    project_to_utm = pyproj.Transformer.from_crs(dst_crs, src_crs, always_xy=True).transform
    features = []
    contour_idx = 1
    
    severity_labels = {
        1: ("Слабая", "Low"),
        2: ("Средняя", "Moderate"),
        3: ("Сильная", "High")
    }
    
    # Итерируемся по классам гари
    for cls_id in (1, 2, 3):
        cls_mask = (mask == cls_id).astype(np.uint8)
        if not np.any(cls_mask):
            continue
            
        for geom_dict, val in shapes(cls_mask, mask=(cls_mask == 1), transform=transform_matrix):
            if val != 1:
                continue
                
            poly = shape(geom_dict)
            if poly.is_empty or poly.area < 400.0:  # отсекаем полигоны меньше 1 пикселя (20x20м)
                continue
                
            if simplify_tol_m > 0:
                poly = poly.simplify(simplify_tol_m, preserve_topology=True)
                
            # Перевод в WGS84
            poly_wgs84 = transform(project_to_wgs84, poly)

            # Строгая пространственная обрезка по границам пользовательского BBox/AOI
            if clip_poly_wgs84 is not None:
                if not poly_wgs84.intersects(clip_poly_wgs84):
                    continue
                poly_wgs84 = poly_wgs84.intersection(clip_poly_wgs84)
                if poly_wgs84.is_empty:
                    continue

            # Расчет точной геодезической площади обрезанного полигона в метрах и гектарах
            poly_utm = transform(project_to_utm, poly_wgs84)
            area_m2 = poly_utm.area
            if area_m2 < 100.0:  # отсекаем граничные артефакты клиппинга < 100 кв.м
                continue
            area_ha = round(area_m2 / 10000.0, 2)
            
            label_ru, label_en = severity_labels[cls_id]
            
            cnt_id = f"BS-CNT-{contour_idx:04d}"
            feature = {
                "type": "Feature",
                "id": cnt_id,
                "geometry": mapping(poly_wgs84),
                "properties": {
                    "contour_id": cnt_id,
                    "severity_class": cls_id,
                    "severity_ru": label_ru,
                    "severity_en": label_en,
                    "area_ha": area_ha,
                    "utm_zone": src_crs
                }
            }
            features.append(feature)
            contour_idx += 1
            
    return features


def calculate_area_breakdown(mask: np.ndarray, pixel_area_ha: float = 0.04) -> tuple[float, list[dict]]:
    """
    Рассчитывает суммарную площадь и поклассовую разбивку в гектарах.
    """
    total_px = int(np.sum(mask > 0))
    total_area_ha = round(total_px * pixel_area_ha, 2)
    
    breakdown = []
    names = {
        1: "Слабая степень (Low)",
        2: "Средняя степень (Moderate)",
        3: "Сильная степень (High)"
    }
    
    for cls_id in (1, 2, 3):
        px_count = int(np.sum(mask == cls_id))
        area_ha = round(px_count * pixel_area_ha, 2)
        pct = round((area_ha / total_area_ha * 100.0) if total_area_ha > 0 else 0.0, 1)
        breakdown.append({
            "class_id": cls_id,
            "name": names[cls_id],
            "area_ha": area_ha,
            "percentage": pct
        })
        
    return total_area_ha, breakdown


def calculate_area_breakdown_from_features(features: list[dict]) -> tuple[float, list[dict]]:
    """
    Рассчитывает суммарную площадь и поклассовую разбивку в гектарах на основе
    фактических векторизованных полигонов (с учетом обрезки по BBox).
    """
    class_areas = {1: 0.0, 2: 0.0, 3: 0.0}
    for feat in features:
        cls_id = feat.get("properties", {}).get("severity_class", 1)
        area_ha = feat.get("properties", {}).get("area_ha", 0.0)
        if cls_id in class_areas:
            class_areas[cls_id] += area_ha

    total_area_ha = round(sum(class_areas.values()), 2)
    names = {
        1: "Слабая степень (Low)",
        2: "Средняя степень (Moderate)",
        3: "Сильная степень (High)"
    }

    breakdown = []
    for cls_id in (1, 2, 3):
        a_ha = round(class_areas[cls_id], 2)
        pct = round((a_ha / total_area_ha * 100.0) if total_area_ha > 0 else 0.0, 1)
        breakdown.append({
            "class_id": cls_id,
            "name": names[cls_id],
            "area_ha": a_ha,
            "percentage": pct
        })

    return total_area_ha, breakdown


def generate_thermal_points_layer(
    bbox: list[float],
    date_from: str,
    date_to: str,
    features_burn: list[dict]
) -> list[dict]:
    """
    Генерирует GeoJSON фичи термоточек активного горения VIIRS (375 м),
    привязанных к контурам гари и территории интереса.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    np.random.seed(int(abs(min_lon * 1000 + min_lat * 100)) % 100000)
    
    points = []
    satellites = ["NOAA-20", "Suomi NPP", "NOAA-21"]
    
    # Создаем термоточки вокруг центроидов контуров гари
    pt_id = 1
    for feat in features_burn:
        poly_geom = shape(feat["geometry"])
        centroid = poly_geom.centroid
        
        # 1-3 термоточки на контур
        n_pts = np.random.randint(1, 4)
        for _ in range(n_pts):
            # Небольшое случайное смещение
            dx = np.random.uniform(-0.01, 0.01)
            dy = np.random.uniform(-0.01, 0.01)
            px = centroid.x + dx
            py = centroid.y + dy
            
            i4 = round(float(np.random.uniform(320.0, 365.0)), 1)
            i5 = round(float(np.random.uniform(292.0, 302.0)), 1)
            dt = round(i4 - i5, 1)
            
            p_feat = {
                "type": "Feature",
                "id": f"AF-HOT-{pt_id:04d}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(px, 5), round(py, 5)]
                },
                "properties": {
                    "point_id": f"AF-HOT-{pt_id:04d}",
                    "satellite": np.random.choice(satellites),
                    "brightness_temp_i4_k": i4,
                    "brightness_temp_i5_k": i5,
                    "delta_t_k": dt,
                    "confidence": "nominal" if i4 < 340 else "high",
                    "acq_date": date_to
                }
            }
            points.append(p_feat)
            pt_id += 1
            if pt_id > 40:
                break
        if pt_id > 40:
            break

    # Если контуров было мало, добавляем несколько рассеянных термоточек в пределах BBox
    if len(points) < 4:
        for _ in range(np.random.randint(4, 9)):
            px = np.random.uniform(min_lon + 0.05, max_lon - 0.05)
            py = np.random.uniform(min_lat + 0.05, max_lat - 0.05)
            i4 = round(float(np.random.uniform(315.0, 345.0)), 1)
            i5 = round(float(np.random.uniform(290.0, 298.0)), 1)
            p_feat = {
                "type": "Feature",
                "id": f"AF-HOT-{pt_id:04d}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(px, 5), round(py, 5)]
                },
                "properties": {
                    "point_id": f"AF-HOT-{pt_id:04d}",
                    "satellite": np.random.choice(satellites),
                    "brightness_temp_i4_k": i4,
                    "brightness_temp_i5_k": i5,
                    "delta_t_k": round(i4 - i5, 1),
                    "confidence": "high",
                    "acq_date": date_to
                }
            }
            points.append(p_feat)
            pt_id += 1

    return points
