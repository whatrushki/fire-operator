"""
Каталог спутниковых чипов (Spatio-Temporal Scene Catalog)
Обеспечивает пространственно-временной поиск реальных спутниковых сцен
по географическим координатам (BBox / полигон) и временному интервалу.
"""
import os
import math
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import pyproj
from shapely.geometry import box, Polygon

# Пути к обучающим и демонстрационным данным
POSSIBLE_TRAIN_DIRS = [
    os.environ.get("TRAIN_DATA_DIR", ""),
    r"C:\Users\vladg\Desktop\Кейс\fire-train-renamed\train",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Кейс", "fire-train-renamed", "train")),
]

FALLBACK_SAMPLE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "sample_chips")
)


class ChipCatalog:
    def __init__(self):
        self.bs_chips: List[Dict[str, Any]] = []
        self.af_chips: List[Dict[str, Any]] = []
        self.is_loaded = False
        self._load_catalog()

    def _find_train_dir(self) -> Optional[Path]:
        for p in POSSIBLE_TRAIN_DIRS:
            if p and os.path.isdir(p):
                p_path = Path(p)
                if (p_path / "bs" / "meta.csv").exists():
                    return p_path
        return None

    def _load_catalog(self):
        train_path = self._find_train_dir()
        if not train_path:
            print("[ChipCatalog] Train directory not found, will use sample_chips fallback.")
            self.is_loaded = True
            return

        # 1. Загрузка BS чипов
        bs_meta_p = train_path / "bs" / "meta.csv"
        if bs_meta_p.exists():
            try:
                df_bs = pd.read_csv(bs_meta_p)
                for _, r in df_bs.iterrows():
                    if pd.isna(r.get("epsg")) or pd.isna(r.get("x_min")):
                        continue
                    epsg_code = int(r["epsg"])
                    crs_str = f"EPSG:{epsg_code}"
                    
                    # Проекция в WGS84
                    t = pyproj.Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
                    min_lon, min_lat = t.transform(r["x_min"], r["y_min"])
                    max_lon, max_lat = t.transform(r["x_max"], r["y_max"])
                    
                    chip_id = str(r["chip_id"])
                    
                    # Файлы чипа
                    s2_pre = train_path / "bs" / "sentinel2_pre" / f"{chip_id}_Sentinel-2_pre.tif"
                    s2_post = train_path / "bs" / "sentinel2_post" / f"{chip_id}_Sentinel-2_post.tif"
                    s1_pre = train_path / "bs" / "sentinel1_pre" / f"{chip_id}_Sentinel-1_pre.tif"
                    s1_post = train_path / "bs" / "sentinel1_post" / f"{chip_id}_Sentinel-1_post.tif"
                    aux_p = train_path / "bs" / "aux" / f"{chip_id}_AUX.tif"
                    
                    if not (s2_pre.exists() and s2_post.exists()):
                        continue

                    # Даты
                    d_pre = datetime.strptime(str(r["date_pre"]), "%Y-%m-%d").date() if pd.notna(r.get("date_pre")) else None
                    d_post = datetime.strptime(str(r["date_post"]), "%Y-%m-%d").date() if pd.notna(r.get("date_post")) else None

                    self.bs_chips.append({
                        "chip_id": chip_id,
                        "kind": "bs",
                        "epsg": epsg_code,
                        "crs_str": crs_str,
                        "utm_bounds": (r["x_min"], r["y_min"], r["x_max"], r["y_max"]),
                        "wgs_bounds": (min_lon, min_lat, max_lon, max_lat),
                        "center_lon": (min_lon + max_lon) / 2.0,
                        "center_lat": (min_lat + max_lat) / 2.0,
                        "poly_wgs": box(min_lon, min_lat, max_lon, max_lat),
                        "date_pre": d_pre,
                        "date_post": d_post,
                        "burn_area_ha": float(r.get("burn_area_ha", 0.0)) if pd.notna(r.get("burn_area_ha")) else 0.0,
                        "fire_event_id": str(r.get("fire_event_id", "")),
                        "files": {
                            "s2_pre": str(s2_pre),
                            "s2_post": str(s2_post),
                            "s1_pre": str(s1_pre),
                            "s1_post": str(s1_post),
                            "aux": str(aux_p)
                        }
                    })
            except Exception as e:
                print(f"[ChipCatalog] Error loading BS metadata: {e}")

        # 2. Загрузка AF чипов
        af_meta_p = train_path / "af" / "meta.csv"
        if af_meta_p.exists():
            try:
                df_af = pd.read_csv(af_meta_p)
                for _, r in df_af.iterrows():
                    if pd.isna(r.get("epsg")) or pd.isna(r.get("x_min")):
                        continue
                    epsg_code = int(r["epsg"])
                    crs_str = f"EPSG:{epsg_code}"
                    t = pyproj.Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
                    min_lon, min_lat = t.transform(r["x_min"], r["y_min"])
                    max_lon, max_lat = t.transform(r["x_max"], r["y_max"])
                    
                    chip_id = str(r["chip_id"])
                    viirs_p = train_path / "af" / "viirs" / f"{chip_id}_VIIRS_I1-I5.tif"
                    aux_p = train_path / "af" / "aux" / f"{chip_id}_AUX.tif"
                    
                    if not viirs_p.exists():
                        continue
                        
                    acq_dt = None
                    if pd.notna(r.get("acq_datetime")):
                        try:
                            acq_dt = datetime.fromisoformat(str(r["acq_datetime"]).replace("Z", "+00:00"))
                        except Exception:
                            pass

                    n_fire = int(r["n_fire_px"]) if (pd.notna(r.get("n_fire_px")) and r.get("n_fire_px") > 0) else 0

                    self.af_chips.append({
                        "chip_id": chip_id,
                        "kind": "af",
                        "epsg": epsg_code,
                        "crs_str": crs_str,
                        "utm_bounds": (r["x_min"], r["y_min"], r["x_max"], r["y_max"]),
                        "wgs_bounds": (min_lon, min_lat, max_lon, max_lat),
                        "center_lon": (min_lon + max_lon) / 2.0,
                        "center_lat": (min_lat + max_lat) / 2.0,
                        "poly_wgs": box(min_lon, min_lat, max_lon, max_lat),
                        "acq_datetime": acq_dt,
                        "n_fire_px": n_fire,
                        "files": {
                            "viirs": str(viirs_p),
                            "aux": str(aux_p)
                        }
                    })
            except Exception as e:
                print(f"[ChipCatalog] Error loading AF metadata: {e}")

        print(f"[ChipCatalog] Successfully loaded {len(self.bs_chips)} BS chips and {len(self.af_chips)} AF chips from dataset.")
        self.is_loaded = True

    def find_best_bs_chip(
        self,
        user_bbox_poly: Polygon,
        center_lon: float,
        center_lat: float,
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Пространственно-временной поиск наиболее подходящего чипа BS.
        Сначала отбираются чипы, пересекающие BBox пользователя.
        Если пересечений несколько или нет прямых пересечений — ранжирование по расстоянию и близости к целевой дате.
        """
        if not self.bs_chips:
            return None

        candidates = []
        for chip in self.bs_chips:
            # 1. Пространственная метрика
            intersects = user_bbox_poly.intersects(chip["poly_wgs"])
            if intersects:
                inter_area = user_bbox_poly.intersection(chip["poly_wgs"]).area
                spatial_dist_deg = 0.0
            else:
                inter_area = 0.0
                dx = center_lon - chip["center_lon"]
                dy = center_lat - chip["center_lat"]
                spatial_dist_deg = math.sqrt(dx * dx + dy * dy)

            # 2. Временная метрика
            if target_date and chip["date_post"]:
                days_diff = abs((chip["date_post"] - target_date).days)
            else:
                days_diff = 100.0

            candidates.append({
                "chip": chip,
                "intersects": intersects,
                "inter_area": inter_area,
                "spatial_dist_deg": spatial_dist_deg,
                "days_diff": days_diff
            })

        # Приоритет: пересекающиеся с BBox
        intersecting = [c for c in candidates if c["intersects"]]
        if intersecting:
            # Сортировка: максимальное пересечение, затем минимальная разница дат
            intersecting.sort(key=lambda x: (-x["inter_area"], x["days_diff"]))
            return intersecting[0]["chip"]

        # Если прямого пересечения нет, но пользователь навел в радиусе 1.5 градусов (~150 км)
        candidates.sort(key=lambda x: (x["spatial_dist_deg"], x["days_diff"]))
        best_nearby = candidates[0]
        if best_nearby["spatial_dist_deg"] <= 1.5:
            return best_nearby["chip"]

        return None

    def find_matching_af_chip(
        self,
        user_bbox_poly: Polygon,
        center_lon: float,
        center_lat: float,
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """Поиск подходящего AF чипа по BBox и дате."""
        if not self.af_chips:
            return None

        candidates = []
        for chip in self.af_chips:
            intersects = user_bbox_poly.intersects(chip["poly_wgs"])
            if intersects:
                inter_area = user_bbox_poly.intersection(chip["poly_wgs"]).area
                spatial_dist_deg = 0.0
            else:
                inter_area = 0.0
                dx = center_lon - chip["center_lon"]
                dy = center_lat - chip["center_lat"]
                spatial_dist_deg = math.sqrt(dx * dx + dy * dy)

            if target_date and chip["acq_datetime"]:
                chip_d = chip["acq_datetime"].date()
                days_diff = abs((chip_d - target_date).days)
            else:
                days_diff = 100.0

            candidates.append({
                "chip": chip,
                "intersects": intersects,
                "inter_area": inter_area,
                "spatial_dist_deg": spatial_dist_deg,
                "days_diff": days_diff
            })

        intersecting = [c for c in candidates if c["intersects"]]
        if intersecting:
            with_fire = [c for c in intersecting if c["chip"]["n_fire_px"] > 0]
            if with_fire:
                with_fire.sort(key=lambda x: (x["days_diff"], -x["inter_area"]))
                return with_fire[0]["chip"]
            intersecting.sort(key=lambda x: (x["days_diff"], -x["inter_area"]))
            return intersecting[0]["chip"]

        # Если прямого пересечения нет, но ищем пожар в окрестности
        with_fire_all = [c for c in candidates if c["chip"]["n_fire_px"] > 0 and c["spatial_dist_deg"] <= 1.5]
        if with_fire_all:
            with_fire_all.sort(key=lambda x: (x["spatial_dist_deg"], x["days_diff"]))
            return with_fire_all[0]["chip"]

        candidates.sort(key=lambda x: (x["spatial_dist_deg"], x["days_diff"]))
        if candidates[0]["spatial_dist_deg"] <= 2.0:
            return candidates[0]["chip"]

        return None

    def get_featured_presets(self) -> List[Dict[str, Any]]:
        """
        Возвращает список ключевых реальных пожаров из обучающей базы
        для удобного интерактивного выбора в UI.
        """
        presets = [
            {
                "id": "volgograd_huge_2022",
                "name": "Волгоград (август 2022, 3350 га)",
                "chip_id": "BS_tr_000109",
                "bbox": [46.12, 49.50, 46.34, 49.68],
                "date_from": "2022-08-10",
                "date_to": "2022-08-28",
                "event_id": "FE13548",
                "desc": "Крупный степной пожар в Заволжье (Палласовский р-н)"
            },
            {
                "id": "astrakhan_max_2022",
                "name": "Астрахань / Каспий (июль 2022, 5878 га)",
                "chip_id": "BS_tr_000095",
                "bbox": [47.05, 48.00, 47.26, 48.20],
                "date_from": "2022-06-20",
                "date_to": "2022-07-10",
                "event_id": "FE12837",
                "desc": "Рекордная по площади гарь в полупустынной зоне"
            },
            {
                "id": "rostov_salsk_2019",
                "name": "Ростовская обл. (август 2019, 4291 га)",
                "chip_id": "BS_tr_000006",
                "bbox": [41.36, 45.98, 41.58, 46.16],
                "date_from": "2019-08-15",
                "date_to": "2019-09-01",
                "event_id": "FE02117",
                "desc": "Масштабный пал суходольной растительности (Сальский р-н)"
            },
            {
                "id": "volgograd_north_2020",
                "name": "Волгоград / Север (июль 2020, 3596 га)",
                "chip_id": "BS_tr_000024",
                "bbox": [42.84, 49.86, 43.06, 50.04],
                "date_from": "2020-07-01",
                "date_to": "2020-07-15",
                "event_id": "FE05085",
                "desc": "Смешанный пожар в пойме реки Медведица"
            },
            {
                "id": "kalmykia_border_2024",
                "name": "Калмыкия / Юг (июль 2024, 3813 га)",
                "chip_id": "BS_tr_000221",
                "bbox": [41.91, 46.33, 42.14, 46.52],
                "date_from": "2024-07-05",
                "date_to": "2024-07-22",
                "event_id": "FE31014",
                "desc": "Свежий крупный пожар пожароопасного сезона 2024 года"
            }
        ]
        return presets


# Глобальный инстанс каталога
catalog = ChipCatalog()
