"""
Pydantic схемы данных для REST API Fire-Operator с расширенной спецификацией OpenAPI/Swagger.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class GeoPolygon(BaseModel):
    """Полигон в формате GeoJSON (WGS84, RFC 7946)."""
    type: str = Field(
        default="Polygon",
        description="Тип геометрии GeoJSON. Должен быть 'Polygon'.",
        example="Polygon"
    )
    coordinates: List[List[List[float]]] = Field(
        ...,
        description="Координаты вершин полигона [[[lon, lat], ...]] в проекции WGS84 (EPSG:4326). Первая и последняя точка должны совпадать.",
        example=[[
            [43.85, 47.25],
            [44.30, 47.25],
            [44.30, 47.70],
            [43.85, 47.70],
            [43.85, 47.25]
        ]]
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
        description="Ограничивающий прямоугольник (BBox) в формате [min_lon, min_lat, max_lon, max_lat] в градусах WGS84.",
        example=[43.0, 47.0, 45.5, 48.5]
    )
    date_from: str = Field(
        ...,
        description="Начальная дата периода анализа (формат YYYY-MM-DD).",
        example="2024-05-01"
    )
    date_to: str = Field(
        ...,
        description="Конечная дата периода анализа (формат YYYY-MM-DD).",
        example="2024-09-30"
    )
    include_radar: bool = Field(
        default=True,
        description="Флаг использования радиолокационных каналов Sentinel-1 SAR (VV/VH) для верификации контуров сквозь дым и облака.",
        example=True
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
    task_id: str = Field(..., description="Уникальный идентификатор задачи анализа", example="tsk_89f0a2c1")
    status: str = Field(default="processing", description="Текущий статус выполнения задачи", example="processing")
    estimated_time_sec: float = Field(..., description="Оценочное время обработки в секундах", example=3.5)
    message: str = Field(..., description="Информационное сообщение системы", example="Запрос принят в обработку.")


class TaskStatusResponse(BaseModel):
    """Статус выполнения фоновой задачи."""
    task_id: str = Field(..., description="Идентификатор задачи", example="tsk_89f0a2c1")
    status: str = Field(..., description="Статус: processing, completed или failed", example="completed")
    progress: int = Field(..., description="Процент завершения (0..100)", example=100)
    created_at: str = Field(..., description="Время создания задачи (ISO 8601)", example="2026-09-18T14:30:00Z")
    completed_at: Optional[str] = Field(None, description="Время завершения обработки", example="2026-09-18T14:30:03Z")


class SeverityBreakdown(BaseModel):
    """Статистика по конкретной степени поражения растительности."""
    class_id: int = Field(..., description="Идентификатор класса: 1 — слабая, 2 — средняя, 3 — сильная", example=1)
    name: str = Field(..., description="Наименование степени поражения", example="Слабая степень (Low)")
    area_ha: float = Field(..., description="Площадь гари данной степени в гектарах", example=454.40)
    percentage: float = Field(..., description="Доля в процентах от суммарной выгоревшей площади", example=99.9)


class AnalyticalReport(BaseModel):
    """Официальная аналитическая справка по территории мониторинга."""
    task_id: str = Field(..., description="Идентификатор задачи", example="tsk_89f0a2c1")
    period: str = Field(..., description="Временной интервал анализа", example="2024-05-01 — 2024-09-30")
    total_burned_area_ha: float = Field(..., description="Суммарная площадь, пройденная огнём (в гектарах)", example=454.80)
    breakdown: List[SeverityBreakdown] = Field(..., description="Детализация по 3 степеням поражения")
    active_thermal_anomalies_count: int = Field(..., description="Число подтвержденных термоточек активного горения (AF)", example=14)
    utm_zone: str = Field(..., description="Проекция UTM, в которой выполнялся расчет площади", example="EPSG:32638")
    spatial_resolution_m: float = Field(default=20.0, description="Пространственное разрешение исходных данных (м/пикс)", example=20.0)
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
    status: str = Field(default="healthy", description="Общий статус системы", example="healthy")
    version: str = Field(..., description="Версия API сервиса", example="1.0.0")
    models_loaded: Dict[str, bool] = Field(
        ...,
        description="Статус загрузки весов ML-моделей (af_model, bs_model)",
        example={"af_model": True, "bs_model": True}
    )
    storage_accessible: bool = Field(..., description="Доступность дискового хранилища артефактов", example=True)


class ErrorDetail(BaseModel):
    """Схема описания ошибки API."""
    detail: str = Field(..., description="Текстовое описание причины ошибки", example="Задача не найдена")
