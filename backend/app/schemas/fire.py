"""
Pydantic схемы данных для REST API Fire-Operator со спецификацией OpenAPI 3.1.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class GeoPolygon(BaseModel):
    """Полигон в формате GeoJSON (WGS84, RFC 7946)."""
    type: str = Field(
        default="Polygon",
        description="Тип геометрии GeoJSON. Должен быть 'Polygon'."
    )
    coordinates: List[List[List[float]]] = Field(
        ...,
        description="Координаты вершин полигона [[[lon, lat], ...]] в проекции WGS84 (EPSG:4326). Первая и последняя точка должны совпадать."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "Polygon",
                "coordinates": [[
                    [43.85, 47.25],
                    [44.30, 47.25],
                    [44.30, 47.70],
                    [43.85, 47.70],
                    [43.85, 47.25]
                ]]
            }
        }
    )


class SpatialTemporalRequest(BaseModel):
    """Параметры пространственно-временного запроса на мониторинг пожаров."""
    polygon: Optional[GeoPolygon] = Field(
        None,
        description="Произвольный полигон исследуемой территории в формате GeoJSON."
    )
    bbox: Optional[List[float]] = Field(
        None,
        description="Ограничивающий прямоугольник (BBox) в формате [min_lon, min_lat, max_lon, max_lat] в градусах WGS84."
    )
    date_from: str = Field(
        ...,
        description="Начальная дата периода анализа (формат YYYY-MM-DD)."
    )
    date_to: str = Field(
        ...,
        description="Конечная дата периода анализа (формат YYYY-MM-DD)."
    )
    include_radar: bool = Field(
        default=True,
        description="Флаг использования радиолокационных каналов Sentinel-1 SAR (VV/VH) для верификации контуров сквозь дым и облака."
    )
    region: Optional[str] = Field(
        default=None,
        description="Кодовое наименование региона (volgograd, kalmykia, rostov, astrakhan или custom)."
    )
    data_source: Optional[str] = Field(
        default=None,
        description="Источник данных: 'offline' (архив чипов), 'online' (NASA FIRMS + Copernicus CDSE), 'hybrid' (онлайн с fallback). При None берётся из конфига сервера."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bbox": [43.0, 47.0, 45.5, 48.5],
                "date_from": "2024-05-01",
                "date_to": "2024-09-30",
                "include_radar": True
            }
        }
    )


class TaskInitResponse(BaseModel):
    """Ответ на постановку задачи мониторинга."""
    task_id: str = Field(..., description="Уникальный идентификатор задачи анализа")
    status: str = Field(default="processing", description="Текущий статус выполнения задачи")
    estimated_time_sec: float = Field(..., description="Оценочное время обработки в секундах")
    message: str = Field(..., description="Информационное сообщение системы")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "tsk_89f0a2c1",
                "status": "processing",
                "estimated_time_sec": 2.5,
                "message": "Запрос принят. Выполняется анализ спутниковых данных Sentinel-2, Sentinel-1 и VIIRS."
            }
        }
    )


class TaskStatusResponse(BaseModel):
    """Статус выполнения фоновой задачи."""
    task_id: str = Field(..., description="Идентификатор задачи")
    status: str = Field(..., description="Статус: processing, completed или failed")
    progress: int = Field(..., description="Процент завершения (0..100)")
    created_at: str = Field(..., description="Время создания задачи (ISO 8601)")
    completed_at: Optional[str] = Field(None, description="Время завершения обработки")
    error: Optional[str] = Field(None, description="Описание ошибки при сбое выполнения задачи")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "tsk_89f0a2c1",
                "status": "completed",
                "progress": 100,
                "created_at": "2026-09-18T14:30:00Z",
                "completed_at": "2026-09-18T14:30:03Z",
                "error": None
            }
        }
    )


class SeverityBreakdown(BaseModel):
    """Статистика по конкретной степени поражения растительности."""
    class_id: int = Field(..., description="Идентификатор класса: 1 — слабая, 2 — средняя, 3 — сильная")
    name: str = Field(..., description="Наименование степени поражения")
    area_ha: float = Field(..., description="Площадь гари данной степени в гектарах")
    percentage: float = Field(..., description="Доля в процентах от суммарной выгоревшей площади")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "class_id": 1,
                "name": "Слабая степень (Low)",
                "area_ha": 454.40,
                "percentage": 99.9
            }
        }
    )


class AnalyticalReport(BaseModel):
    """Официальная аналитическая справка по территории мониторинга."""
    task_id: str = Field(..., description="Идентификатор задачи")
    period: str = Field(..., description="Временной интервал анализа")
    total_burned_area_ha: float = Field(..., description="Суммарная площадь, пройденная огнём (в гектарах)")
    breakdown: List[SeverityBreakdown] = Field(..., description="Детализация по 3 степеням поражения")
    active_thermal_anomalies_count: int = Field(..., description="Число подтвержденных термоточек активного горения (AF)")
    utm_zone: str = Field(..., description="Проекция UTM, в которой выполнялся расчет площади")
    spatial_resolution_m: float = Field(default=20.0, description="Пространственное разрешение исходных данных (м/пикс)")
    region: Optional[str] = Field(None, description="Регион мониторинга")
    model_af: Optional[str] = Field(None, description="Использованная модель / источник Active Fire")
    model_bs: Optional[str] = Field(None, description="Использованная модель / источник Burn Severity")
    nearest_scene: Optional[Dict[str, Any]] = Field(None, description="Информация о ближайшей спутниковой сцене при отсутствии прямого перекрытия")
    direct_scene: Optional[Dict[str, Any]] = Field(None, description="Информация о напрямую обработанной сцене Sentinel-2")
    spectral_metrics: Optional[Dict[str, Any]] = Field(None, description="Спектральные метрики растительности (NBR до, NBR после, dNBR)")
    calculation_method: str = Field(
        default="Точный геодезический попиксельный учет проекции UTM (0.04 га/пикс)",
        description="Методика расчета площадей"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "tsk_89f0a2c1",
                "period": "2024-05-01 — 2024-09-30",
                "total_burned_area_ha": 454.80,
                "breakdown": [
                    {"class_id": 1, "name": "Слабая степень (Low)", "area_ha": 454.40, "percentage": 99.9},
                    {"class_id": 2, "name": "Средняя степень (Moderate)", "area_ha": 0.40, "percentage": 0.1},
                    {"class_id": 3, "name": "Сильная степень (High)", "area_ha": 0.00, "percentage": 0.0}
                ],
                "active_thermal_anomalies_count": 14,
                "utm_zone": "EPSG:32638",
                "spatial_resolution_m": 20.0,
                "calculation_method": "Точный геодезический попиксельный учет проекции UTM (0.04 га/пикс)"
            }
        }
    )


class HealthResponse(BaseModel):
    """Схема диагностики состояния сервиса."""
    status: str = Field(default="healthy", description="Общий статус системы")
    version: str = Field(..., description="Версия API сервиса")
    models_loaded: Dict[str, bool] = Field(
        ...,
        description="Статус загрузки весов ML-моделей (af_model, bs_model)"
    )
    storage_accessible: bool = Field(..., description="Доступность дискового хранилища артефактов")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "models_loaded": {"af_model": True, "bs_model": True},
                "storage_accessible": True
            }
        }
    )


class ErrorDetail(BaseModel):
    """Схема описания ошибки API."""
    detail: str = Field(..., description="Текстовое описание причины ошибки")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Задача не найдена"
            }
        }
    )
