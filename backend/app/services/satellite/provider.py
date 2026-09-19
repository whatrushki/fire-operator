"""
Провайдер спутниковых данных (SatelliteDataProvider).
Реализует архитектурный паттерн Hybrid Data Source Switcher, обеспечивая
прозрачное переключение между локальным архивом чипов и онлайн-спутниками
(NASA FIRMS + Copernicus CDSE) с автоматическим fallback.
"""

import logging
from enum import Enum
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings
from app.services.satellite.cache import SceneCache
from app.services.satellite.firms_client import FIRMSClient
from app.services.satellite.cdse_auth import CDSEAuthManager
from app.services.satellite.cdse_client import CDSEClient

logger = logging.getLogger(__name__)


class DataSourceType(str, Enum):
    """Режимы поставки геоданных ДЗЗ."""
    OFFLINE = "offline"  # Локальный архив чипов (гарантирует оффлайн-работу конкурса)
    ONLINE = "online"    # Онлайн спутники (NASA FIRMS + Copernicus CDSE)
    HYBRID = "hybrid"    # Приоритет онлайн, авто-переход на архив при недоступности


class SatelliteDataProvider:
    """
    Единый интерфейс доступа к космическим данным для сервиса Fire-Operator.
    """

    def __init__(self, mode: Optional[str] = None):
        raw_mode = (mode or getattr(settings, "DATA_SOURCE_MODE", "offline")).lower().strip()
        try:
            self.mode = DataSourceType(raw_mode)
        except ValueError:
            logger.warning("[SatelliteProvider] Неизвестный режим '%s', используется OFFLINE.", raw_mode)
            self.mode = DataSourceType.OFFLINE

        # Инициализация дискового кэша
        self.cache = SceneCache(
            cache_dir=settings.SATELLITE_CACHE_DIR,
            ttl_hours=getattr(settings, "SATELLITE_CACHE_TTL_HOURS", 24),
            max_size_gb=getattr(settings, "SATELLITE_CACHE_MAX_GB", 2.0)
        )

        # Клиент активных термоточек NASA FIRMS
        self.firms = FIRMSClient(
            api_key=getattr(settings, "FIRMS_API_KEY", ""),
            cache=self.cache
        )

        # Менеджер авторизации и клиент Copernicus CDSE
        self.cdse_auth = CDSEAuthManager(
            client_id=getattr(settings, "CDSE_CLIENT_ID", ""),
            client_secret=getattr(settings, "CDSE_CLIENT_SECRET", "")
        )
        self.cdse = CDSEClient(
            auth=self.cdse_auth,
            cache=self.cache
        )

    def is_online_enabled(self) -> bool:
        """Проверяет, разрешен ли онлайн-доступ в текущем режиме."""
        return self.mode in (DataSourceType.ONLINE, DataSourceType.HYBRID)

    def get_thermal_points(
        self,
        bbox: Tuple[float, float, float, float],
        date_from: date,
        date_to: date
    ) -> Tuple[Optional[List[Dict[str, Any]]], str, Dict[str, Any]]:
        """
        Получение термоточек активного горения.

        Returns:
            Tuple: (features_list_or_None, source_used_tag, metadata_dict)
            Если возвращается features_list=None, вызывающий код использует
            стандартный локальный инференс модели VIIRS по архивным чипам.
        """
        # 1. Если режим строго оффлайн
        if self.mode == DataSourceType.OFFLINE:
            return None, "offline", {"mode": "offline", "provider": "Local Chip Archive"}

        # 2. Если онлайн или гибрид — пробуем NASA FIRMS
        if self.firms.is_configured():
            try:
                features = self.firms.fetch_active_fires(
                    bbox=bbox,
                    date_from=date_from,
                    date_to=date_to
                )
                if features:
                    meta = {
                        "mode": str(self.mode.value),
                        "provider": "NASA FIRMS (VIIRS NRT)",
                        "count": len(features),
                        "satellites": list({f["properties"]["satellite"] for f in features})
                    }
                    return features, "online_firms", meta

                # Если точек 0, но в режиме строго онлайн — возвращаем честный пустой список
                if self.mode == DataSourceType.ONLINE:
                    meta = {
                        "mode": "online",
                        "provider": "NASA FIRMS (VIIRS NRT)",
                        "count": 0,
                        "satellites": ["VIIRS"]
                    }
                    return [], "online_firms", meta

            except Exception as exc:
                logger.error("[SatelliteProvider] Ошибка запроса к NASA FIRMS: %s", exc)

        # 3. Fallback в режиме HYBRID: если ключа нет или запрос не дал результатов
        if self.mode == DataSourceType.HYBRID:
            logger.info("[SatelliteProvider] Fallback на локальный каталог чипов (режим HYBRID).")
            return None, "offline_fallback", {"mode": "hybrid", "provider": "Local Archive Fallback"}

        # Строгий онлайн без настроенного ключа
        return [], "online_unconfigured", {"mode": "online", "error": "FIRMS API key not configured"}

    def query_available_satellite_scenes(
        self,
        bbox: Tuple[float, float, float, float],
        date_from: date,
        date_to: date
    ) -> Dict[str, Any]:
        """
        Информационный поиск спутниковых сцен Sentinel-2 и Sentinel-1 в каталоге Copernicus CDSE.
        Позволяет отобразить пользователю и операторам реальные доступные пролеты спутников.
        """
        result = {
            "sentinel2_scenes": [],
            "sentinel1_scenes": [],
            "online_available": False,
        }

        if not self.is_online_enabled():
            return result

        try:
            s2_scenes = self.cdse.search_scenes(
                bbox=bbox,
                date_from=date_from,
                date_to=date_to,
                collection="SENTINEL-2",
                max_cloud_cover=35.0,
                top=4
            )
            result["sentinel2_scenes"] = s2_scenes

            s1_scenes = self.cdse.search_scenes(
                bbox=bbox,
                date_from=date_from,
                date_to=date_to,
                collection="SENTINEL-1",
                top=3
            )
            result["sentinel1_scenes"] = s1_scenes
            result["online_available"] = bool(s2_scenes or s1_scenes)
        except Exception as e:
            logger.debug("[SatelliteProvider] Поиск сцен CDSE завершился с ошибкой: %s", e)

        return result

    def get_service_status(self) -> Dict[str, Any]:
        """Диагностический статус подключения к спутниковым провайдерам."""
        return {
            "mode": self.mode.value,
            "firms": {
                "configured": self.firms.is_configured(),
                "service": "NASA FIRMS (VIIRS 375m NRT)",
                "status": "ready" if self.firms.is_configured() else "no_api_key"
            },
            "cdse": {
                "configured": self.cdse_auth.is_configured(),
                "service": "Copernicus Data Space Ecosystem (Sentinel-2/1)",
                "status": "ready" if self.cdse_auth.is_configured() else "no_credentials"
            },
            "cache": {
                "dir": str(self.cache.cache_dir),
                "ttl_hours": self.cache.ttl_seconds // 3600
            }
        }


# Глобальный кэш инстансов провайдеров
_PROVIDER_INSTANCES: Dict[str, SatelliteDataProvider] = {}


def get_satellite_provider(mode: Optional[str] = None) -> SatelliteDataProvider:
    """Возвращает singleton-экземпляр провайдера для заданного режима."""
    effective_mode = (mode or getattr(settings, "DATA_SOURCE_MODE", "offline")).lower().strip()
    if effective_mode not in _PROVIDER_INSTANCES:
        _PROVIDER_INSTANCES[effective_mode] = SatelliteDataProvider(mode=effective_mode)
    return _PROVIDER_INSTANCES[effective_mode]
