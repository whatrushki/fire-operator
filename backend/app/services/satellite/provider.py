"""
Провайдер спутниковых данных (SatelliteDataProvider).
Реализует архитектурный паттерн Hybrid Data Source Switcher, обеспечивая
прозрачное переключение между локальным архивом чипов и онлайн-спутниками
(NASA FIRMS + Copernicus CDSE) с автоматическим fallback.
"""

import socket
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


def check_internet_reachability(timeout_sec: float = 1.5) -> bool:
    """
    Быстрая проверка физического наличия интернета и доступности спутниковых сервисов.
    Проверяет соединение с DNS (1.1.1.1, 8.8.8.8) или хостом Copernicus CDSE.
    """
    targets = [
        ("1.1.1.1", 53),
        ("8.8.8.8", 53),
        ("dataspace.copernicus.eu", 443),
        ("firms.modaps.eosdis.nasa.gov", 443),
    ]
    for host, port in targets:
        try:
            sock = socket.create_connection((host, port), timeout=timeout_sec)
            sock.close()
            return True
        except OSError:
            continue
    return False


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

    def check_reachability(self, timeout_sec: float = 1.5) -> bool:
        """Проверяет физическое наличие соединения с внешним интернетом/спутниками."""
        return check_internet_reachability(timeout_sec=timeout_sec)

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

        # 2. Проверяем доступность интернета
        internet_ok = self.check_reachability()
        if not internet_ok:
            if self.mode == DataSourceType.ONLINE:
                # В строго онлайн-режиме без интернета — никакой подмены архивными данными!
                return [], "online_no_internet", {
                    "mode": "online",
                    "error": "Отсутствует подключение к сети Интернет. Спутниковые данные недоступны.",
                    "count": 0
                }
            # В режиме HYBRID: штатный переход на локальный архив
            logger.warning("[SatelliteProvider] Интернет недоступен, режим HYBRID переходит на локальный архив.")
            return None, "offline_fallback", {
                "mode": "hybrid",
                "provider": "Local Archive Fallback (No Internet)"
            }

        # 3. Если онлайн или гибрид и есть интернет — пробуем NASA FIRMS
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

        # 4. Fallback в режиме HYBRID: если ключа нет или запрос завершился ошибкой
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
        internet_ok = self.check_reachability()
        firms_ready = self.firms.is_configured() and internet_ok
        cdse_ready = (self.cdse_auth.is_configured() or True) and internet_ok

        return {
            "mode": self.mode.value,
            "internet_available": internet_ok,
            "online_ready": internet_ok and (self.firms.is_configured() or self.cdse_auth.is_configured()),
            "firms": {
                "configured": self.firms.is_configured(),
                "service": "NASA FIRMS (VIIRS 375m NRT)",
                "status": "ready" if firms_ready else ("no_internet" if not internet_ok else "no_api_key")
            },
            "cdse": {
                "configured": self.cdse_auth.is_configured(),
                "open_catalog": True,
                "service": "Copernicus Data Space Ecosystem (Sentinel-2/1)",
                "status": "ready" if cdse_ready else ("no_internet" if not internet_ok else "unreachable")
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
