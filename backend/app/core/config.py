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

    model_config = ConfigDict(case_sensitive=True)


settings = Settings()
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.TEMPLATES_DIR, exist_ok=True)
