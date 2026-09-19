"""
Конфигурация бэкенд-сервиса Fire-Operator.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Fire-Operator: Космический мониторинг природных пожаров"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Пути к директориям
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    PROJECT_ROOT: str = os.path.abspath(os.path.join(BASE_DIR, ".."))
    WEIGHTS_DIR: str = os.path.join(PROJECT_ROOT, "weights")
    STORAGE_DIR: str = os.path.join(BASE_DIR, "storage")
    TEMPLATES_DIR: str = os.path.join(BASE_DIR, "app", "templates")
    
    # Гео-параметры (Юг России)
    DEFAULT_CRS: str = "EPSG:4326"
    PIXEL_SIZE_BS_M: float = 20.0
    PIXEL_AREA_BS_HA: float = 0.04  # (20m * 20m) = 400 m2 = 0.04 ha
    PIXEL_SIZE_AF_M: float = 375.0
    PIXEL_AREA_AF_HA: float = 14.0625  # (375m * 375m) = 140625 m2 = 14.0625 ha

    # Спутниковые API (онлайн-режим)
    # Режим источника данных: "offline" (архив чипов), "online" (NASA FIRMS + Copernicus CDSE), "hybrid" (онлайн с fallback на офлайн)
    DATA_SOURCE_MODE: str = "offline"
    # NASA FIRMS MAP_KEY (бесплатно: https://firms.modaps.eosdis.nasa.gov/api/area/)
    FIRMS_API_KEY: str = ""
    # Copernicus Data Space Ecosystem OAuth2 (бесплатно: https://dataspace.copernicus.eu/)
    CDSE_CLIENT_ID: str = ""
    CDSE_CLIENT_SECRET: str = ""
    # Кэш загруженных спутниковых сцен
    SATELLITE_CACHE_DIR: str = os.path.join(BASE_DIR, "storage", "satellite_cache")
    SATELLITE_CACHE_TTL_HOURS: int = 24
    SATELLITE_CACHE_MAX_GB: float = 2.0

    model_config = ConfigDict(case_sensitive=True, env_file=".env", env_file_encoding="utf-8")


settings = Settings()
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.TEMPLATES_DIR, exist_ok=True)
os.makedirs(settings.SATELLITE_CACHE_DIR, exist_ok=True)
