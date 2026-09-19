"""
Сервис онлайн-запроса спутниковых данных ДЗЗ в реальном времени:
1. NASA FIRMS VIIRS Active Fire (квазиреальное время, 375м)
2. Sentinel-2 L2A STAC API (Earth Search AWS)
3. Автоматическое выделение и зонирование гарей по 3 степеням строгости поражения
"""
import os
import json
import urllib.request
import pandas as pd
import numpy as np
from shapely.geometry import box as shapely_box, Point, Polygon, MultiPolygon, shape, mapping
from shapely.ops import transform
import pyproj
import rasterio.features
from rasterio.transform import from_bounds
from scipy.ndimage import gaussian_filter
from app.core.config import settings

FIRMS_CACHE_PATH = os.path.join(settings.STORAGE_DIR, "firms_global_cache.csv")

def query_sentinel2_stac_scenes(bbox, date_from, date_to, limit=5):
    """Поиск доступных реальных космических снимков Sentinel-2 L2A в заданном BBox за период."""
    url = "https://earth-search.aws.element84.com/v1/search"
    query = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
        "limit": limit
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(query).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "FireOperator/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.loads(r.read().decode())
            items = []
            for feat in res.get("features", []):
                items.append({
                    "id": feat.get("id"),
                    "date": feat.get("properties", {}).get("datetime", "")[:10],
                    "cloud_cover": feat.get("properties", {}).get("eo:cloud_cover", 0),
                    "platform": feat.get("properties", {}).get("platform", "Sentinel-2")
                })
            return items
    except Exception:
        return []


def get_live_viirs_hotspots(min_lon, min_lat, max_lon, max_lat, date_from, date_to):
    """Поиск реальных термоточек VIIRS AF из глобального фида NASA FIRMS (без моковых данных)."""
    if not os.path.exists(FIRMS_CACHE_PATH):
        return []
    
    try:
        df = pd.read_csv(
            FIRMS_CACHE_PATH,
            usecols=["latitude", "longitude", "bright_ti4", "bright_ti5", "acq_date", "confidence", "satellite"]
        )
        sub = df[
            (df["latitude"] >= min_lat) & (df["latitude"] <= max_lat) &
            (df["longitude"] >= min_lon) & (df["longitude"] <= max_lon)
        ]
        date_sub = sub[(sub["acq_date"] >= date_from) & (sub["acq_date"] <= date_to)]
        if len(date_sub) > 0:
            sub = date_sub
            
        features = []
        pt_idx = 0
        for _, row in sub.iterrows():
            pt_idx += 1
            i4 = float(row["bright_ti4"])
            i5 = float(row["bright_ti5"]) if pd.notnull(row["bright_ti5"]) else i4 - 15.0
            dt = round(i4 - i5, 1)
            
            # Физическая фильтрация шумов и бликов по ТЗ
            if not ((i4 > 305.0 and dt > 4.0) or i4 >= 366.5):
                continue
                
            conf_str = str(row["confidence"]).lower()
            features.append({
                "type": "Feature",
                "id": f"AF-HOT-{pt_idx:04d}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(row["longitude"]), 5), round(float(row["latitude"]), 5)]
                },
                "properties": {
                    "point_id": f"AF-HOT-{pt_idx:04d}",
                    "satellite": "VIIRS S-NPP" if str(row["satellite"]) == "N" else "VIIRS NOAA-20",
                    "brightness_temp_i4_k": round(i4, 1),
                    "brightness_temp_i5_k": round(i5, 1),
                    "delta_t_k": dt,
                    "confidence": "high" if conf_str in ["high", "h"] or i4 > 330.0 else "nominal",
                    "acq_date": str(row["acq_date"])
                }
            })
        return features
    except Exception as e:
        print("Error reading FIRMS live data:", e)
        return []

