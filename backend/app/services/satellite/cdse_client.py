"""
Клиент для работы с данными Copernicus Data Space Ecosystem (CDSE).
Поддерживает поиск спутниковых снимков через OData Catalog API
и скачивание спектральных каналов Sentinel-2 / Sentinel-1 через Process API.
"""

import io
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Tuple

import httpx
import numpy as np

from app.services.satellite.cache import SceneCache
from app.services.satellite.cdse_auth import CDSEAuthManager

logger = logging.getLogger(__name__)


class CDSEClient:
    """
    Клиент для каталога и вычислений Copernicus Data Space Ecosystem (CDSE).
    Документация: https://dataspace.copernicus.eu/analyse/apis
    """

    CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
    PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

    def __init__(
        self,
        auth: Optional[CDSEAuthManager] = None,
        cache: Optional[SceneCache] = None,
        timeout_sec: float = 30.0
    ):
        self.auth = auth
        self.cache = cache
        self.timeout_sec = timeout_sec

    def is_configured(self) -> bool:
        """Проверяет готовность клиента к авторизованным запросам."""
        return bool(self.auth and self.auth.is_configured())

    def search_scenes(
        self,
        bbox: Tuple[float, float, float, float],
        date_from: date,
        date_to: date,
        collection: str = "SENTINEL-2",
        max_cloud_cover: float = 30.0,
        top: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Поиск космических снимков в открытом каталоге Copernicus OData.
        Доступен публично (не требует платной подписки).

        Args:
            bbox: (min_lon, min_lat, max_lon, max_lat) в WGS84
            date_from: начало интервала
            date_to: конец интервала
            collection: 'SENTINEL-2' или 'SENTINEL-1'
            max_cloud_cover: максимальный процент облачности
            top: максимальное количество найденных сцен

        Returns:
            Список описаний сцен: ID, наименование, дата, облачность, геометрия.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        poly_wkt = (
            f"SRID=4326;POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
            f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
        )

        d_from_str = f"{date_from.strftime('%Y-%m-%d')}T00:00:00.000Z"
        d_to_str = f"{date_to.strftime('%Y-%m-%d')}T23:59:59.999Z"

        # Формирование OData фильтра
        filters = [
            f"Collection/Name eq '{collection}'",
            f"OData.CSC.Intersects(area=geography'{poly_wkt}')",
            f"ContentDate/Start gt {d_from_str}",
            f"ContentDate/Start lt {d_to_str}",
        ]

        if collection == "SENTINEL-2":
            filters.append(
                f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/Value lt {max_cloud_cover})"
            )

        filter_str = " and ".join(filters)
        params = {
            "$filter": filter_str,
            "$orderby": "ContentDate/Start desc",
            "$top": str(top),
        }

        # Проверка кэша поиска
        cache_key = None
        if self.cache:
            cache_key = self.cache.generate_key("cdse_search", collection, str(bbox), str(date_from), str(date_to))
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                return cached

        logger.info("[CDSEClient] Поиск сцен %s в каталоге Copernicus OData...", collection)
        scenes = []

        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.get(self.CATALOG_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    value_list = data.get("value", [])

                    for item in value_list:
                        item_id = item.get("Id")
                        item_name = item.get("Name", "")
                        content_date = item.get("ContentDate", {})
                        start_date = content_date.get("Start", "")

                        cloud_pct = 0.0
                        for att in item.get("Attributes", []):
                            if att.get("Name") == "cloudCover":
                                cloud_pct = float(att.get("Value", 0.0))
                                break

                        scenes.append({
                            "id": item_id,
                            "name": item_name,
                            "collection": collection,
                            "datetime": start_date,
                            "cloud_cover": round(cloud_pct, 1),
                            "origin": "Copernicus CDSE OData"
                        })
                else:
                    logger.warning("[CDSEClient] OData API вернул код %d: %s", resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.error("[CDSEClient] Ошибка обращения к OData каталогу CDSE: %s", exc)

        if self.cache and cache_key:
            self.cache.put_json(cache_key, scenes, extra_meta={"count": len(scenes)})

        logger.info("[CDSEClient] Найдено %d подходящих сцен %s.", len(scenes), collection)
        return scenes

    def fetch_sentinel2_bands(
        self,
        bbox: Tuple[float, float, float, float],
        date_from: date,
        date_to: date,
        width: int = 512,
        height: int = 512
    ) -> Optional[Tuple[Dict[str, Any], np.ndarray]]:
        """
        Запрашивает 10 спектральных каналов Sentinel-2 L2A через Sentinel Hub Process API.
        Возвращает массив shape (10, height, width) со значениями INT16 (DN reflectance * 10000).
        Каналы соответствуют входному формату ML-модели BS:
        [B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12].
        """
        if not self.is_configured():
            logger.warning("[CDSEClient] Аутентификация CDSE не настроена. Скачивание спектральных каналов недоступно.")
            return None

        token = self.auth.get_access_token() if self.auth else None
        if not token:
            logger.warning("[CDSEClient] Не удалось получить токен CDSE.")
            return None

        min_lon, min_lat, max_lon, max_lat = bbox
        time_from = f"{date_from.strftime('%Y-%m-%d')}T00:00:00Z"
        time_to = f"{date_to.strftime('%Y-%m-%d')}T23:59:59Z"

        evalscript = """//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"],
      units: "DN"
    }],
    output: {
      bands: 10,
      sampleType: "INT16"
    }
  };
}

function evaluatePixel(sample) {
  return [
    sample.B02, sample.B03, sample.B04, sample.B05,
    sample.B06, sample.B07, sample.B08, sample.B8A,
    sample.B11, sample.B12
  ];
}
"""

        payload = {
            "input": {
                "bounds": {
                    "bbox": [min_lon, min_lat, max_lon, max_lat],
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
                },
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": time_from, "to": time_to},
                        "maxCloudCoverage": 30
                    }
                }]
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]
            },
            "evalscript": evalscript
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "image/tiff"
        }

        # Проверка кэша растра
        cache_key = None
        if self.cache:
            cache_key = self.cache.generate_key("cdse_s2", str(bbox), time_from, time_to, width, height)
            cached_path = self.cache.get_file_path(cache_key, "s2_bands.tif")
            if cached_path and cached_path.exists():
                try:
                    import rasterio
                    with rasterio.open(cached_path) as src:
                        arr = src.read()
                    meta = self.cache.get_json(cache_key) or {}
                    logger.info("[CDSEClient] Спектральные каналы Sentinel-2 загружены из дискового кэша.")
                    return meta, arr
                except Exception as read_err:
                    logger.warning("[CDSEClient] Ошибка чтения кэшированного GeoTIFF: %s", read_err)

        try:
            logger.info("[CDSEClient] Запрос спектральных каналов Sentinel-2 через Process API...")
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.post(self.PROCESS_URL, json=payload, headers=headers)

                if resp.status_code == 200:
                    import rasterio
                    with rasterio.open(io.BytesIO(resp.content)) as src:
                        bands_arr = src.read()

                    meta = {
                        "source": "Copernicus Sentinel-2 L2A (CDSE Process API)",
                        "bbox": bbox,
                        "date_from": str(date_from),
                        "date_to": str(date_to),
                        "bands_count": int(bands_arr.shape[0]),
                        "dimensions": [int(bands_arr.shape[1]), int(bands_arr.shape[2])]
                    }

                    if self.cache and cache_key:
                        self.cache.put_file(cache_key, "s2_bands.tif", resp.content, extra_meta=meta)
                        self.cache.put_json(cache_key, meta)

                    logger.info("[CDSEClient] Спектральные каналы Sentinel-2 успешно получены (shape=%s).", bands_arr.shape)
                    return meta, bands_arr
                else:
                    logger.warning("[CDSEClient] Process API вернул ошибку %d: %s", resp.status_code, resp.text[:200])
                    return None
        except Exception as exc:
            logger.error("[CDSEClient] Сбой при вызове Process API Sentinel-2: %s", exc)
            return None
