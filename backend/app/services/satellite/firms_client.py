"""
Клиент NASA FIRMS API (Fire Information for Resource Management System).
Обеспечивает получение оперативных (NRT) и архивных данных активных пожаров
радиометра VIIRS (375 м) с космических аппаратов Suomi NPP, NOAA-20 и NOAA-21.
"""

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.services.satellite.cache import SceneCache

logger = logging.getLogger(__name__)


class FIRMSClient:
    """
    Клиент для взаимодействия с REST API сервиса NASA FIRMS.
    Документация: https://firms.modaps.eosdis.nasa.gov/api/area/
    """

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(
        self,
        api_key: str = "",
        cache: Optional[SceneCache] = None,
        timeout_sec: float = 12.0
    ):
        self.api_key = api_key.strip()
        self.cache = cache
        self.timeout_sec = timeout_sec

    def is_configured(self) -> bool:
        """Проверяет, задан ли API-ключ NASA FIRMS."""
        return bool(self.api_key)

    def fetch_active_fires(
        self,
        bbox: Tuple[float, float, float, float],
        date_from: date,
        date_to: date,
        source: str = "VIIRS_SNPP_NRT",
        min_confidence: str = "nominal"
    ) -> List[Dict[str, Any]]:
        """
        Запрашивает термоточки активного горения для заданного BBox и диапазона дат.

        Args:
            bbox: (min_lon, min_lat, max_lon, max_lat) в WGS84
            date_from: начальная дата наблюдения
            date_to: конечная дата наблюдения
            source: источник данных (VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT, VIIRS_NOAA21_NRT)
            min_confidence: минимальный уровень достоверности ("low", "nominal", "high")

        Returns:
            Список GeoJSON Feature словарей в формате термоточек Fire-Operator.
        """
        if not self.is_configured():
            logger.warning("[FIRMSClient] API ключ не задан. Онлайн-запрос термоточек пропущен.")
            return []

        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_str = f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"

        # Проверяем кэш
        cache_key = None
        if self.cache:
            cache_key = self.cache.generate_key("firms", bbox_str, str(date_from), str(date_to), source)
            cached_result = self.cache.get_json(cache_key)
            if cached_result is not None:
                logger.info("[FIRMSClient] Возврат термоточек из дискового кэша (%d точек).", len(cached_result))
                return cached_result

        # Вычисляем day_range и начальную дату
        # FIRMS Area API принимает /api/area/csv/{MAP_KEY}/{source}/{bbox}/{day_range}/{date}
        delta_days = (date_to - date_from).days + 1
        day_range = max(1, min(10, delta_days))
        date_str = date_from.strftime("%Y-%m-%d")

        url = f"{self.BASE_URL}/{self.api_key}/{source}/{bbox_str}/{day_range}/{date_str}"
        logger.info("[FIRMSClient] Запрос к NASA FIRMS: source=%s, bbox=%s, range=%d, date=%s", source, bbox_str, day_range, date_str)

        raw_csv_text = ""
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    raw_csv_text = resp.text
                elif resp.status_code == 401 or "Invalid Map Key" in resp.text:
                    logger.error("[FIRMSClient] Недействительный ключ NASA FIRMS API key.")
                    return []
                else:
                    logger.warning("[FIRMSClient] Ошибка HTTP %d от FIRMS: %s", resp.status_code, resp.text[:200])
                    return []
        except Exception as exc:
            logger.error("[FIRMSClient] Сбой сетевого соединения с NASA FIRMS: %s", exc)
            return []

        features = self._parse_firms_csv(
            csv_text=raw_csv_text,
            bbox=bbox,
            min_confidence=min_confidence
        )

        # Сохраняем в кэш при успехе
        if self.cache and cache_key:
            self.cache.put_json(cache_key, features, extra_meta={"count": len(features)})

        logger.info("[FIRMSClient] Успешно получено %d термоточек от NASA FIRMS.", len(features))
        return features

    def _parse_firms_csv(
        self,
        csv_text: str,
        bbox: Tuple[float, float, float, float],
        min_confidence: str = "nominal"
    ) -> List[Dict[str, Any]]:
        """Парсинг CSV ответа FIRMS в GeoJSON Feature-коллекцию."""
        if not csv_text or "latitude" not in csv_text:
            return []

        min_lon, min_lat, max_lon, max_lat = bbox
        conf_rank = {"low": 1, "nominal": 2, "high": 3}
        min_rank = conf_rank.get(min_confidence.lower(), 2)

        features = []
        reader = csv.DictReader(io.StringIO(csv_text.strip()))

        pt_idx = 1
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])

                # Проверка вхождения в границы
                if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                    continue

                conf_raw = row.get("confidence", "nominal").lower()
                # Для VIIRS confidence бывает: 'low', 'nominal', 'high' или процентное число
                if conf_raw.isdigit():
                    val = int(conf_raw)
                    conf_level = "high" if val >= 80 else ("nominal" if val >= 40 else "low")
                else:
                    conf_level = conf_raw

                if conf_rank.get(conf_level, 2) < min_rank:
                    continue

                bright_ti4 = float(row.get("bright_ti4", row.get("brightness", 320.0)))
                bright_ti5 = float(row.get("bright_ti5", row.get("bright_t31", bright_ti4 - 15.0)))
                delta_t = round(bright_ti4 - bright_ti5, 1)
                frp = float(row.get("frp", 0.0))
                sat_name = row.get("satellite", "VIIRS/Suomi-NPP")
                acq_d = row.get("acq_date", "")
                acq_t = row.get("acq_time", "")
                acq_str = f"{acq_d} {acq_t[:2]}:{acq_t[2:]}".strip() if acq_t else acq_d

                feat = {
                    "type": "Feature",
                    "id": f"AF-FIRMS-{pt_idx:04d}",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [round(lon, 5), round(lat, 5)]
                    },
                    "properties": {
                        "point_id": f"AF-FIRMS-{pt_idx:04d}",
                        "satellite": sat_name,
                        "brightness_temp_i4_k": round(bright_ti4, 1),
                        "brightness_temp_i5_k": round(bright_ti5, 1),
                        "delta_t_k": delta_t,
                        "confidence": conf_level,
                        "frp": round(frp, 1),
                        "acq_date": acq_str,
                        "source": "NASA FIRMS (VIIRS NRT)"
                    }
                }
                features.append(feat)
                pt_idx += 1

                if len(features) >= 300:
                    break
            except (ValueError, KeyError) as parse_err:
                logger.debug("Пропуск строки CSV FIRMS: %s", parse_err)
                continue

        return features
