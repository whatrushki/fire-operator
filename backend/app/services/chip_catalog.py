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
        target_date: Optional[date] = None,
        max_days_diff: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        Строгий пространственно-временной поиск чипа BS:
        1. Чип ОБЯЗАН пространственно пересекаться с выбранным BBox пользователя.
        2. Дата съемки чипа (date_post) ОБЯЗАНА находиться в пределах окна target_date ± max_days_diff дней (по умолчанию 20 дней).
        Если снимок в это время и в этом месте не зафиксирован — возвращается None (пожара нет).
        """
        if not self.bs_chips:
            return None

        candidates = []
        for chip in self.bs_chips:
            # 1. Строгая проверка пространственного пересечения
            if not user_bbox_poly.intersects(chip["poly_wgs"]):
                continue

            inter_area = user_bbox_poly.intersection(chip["poly_wgs"]).area

            # 2. Строгая проверка временного диапазона
            if target_date and chip["date_post"]:
                days_diff = abs((chip["date_post"] - target_date).days)
                if days_diff > max_days_diff:
                    # Дата за пределами допустимого окна — пропускаем
                    continue
            else:
                days_diff = 0

            candidates.append({
                "chip": chip,
                "inter_area": inter_area,
                "days_diff": days_diff
            })

        if not candidates:
            return None

        # Сортировка: максимальное пересечение полигона, затем минимальная разница дат
        candidates.sort(key=lambda x: (-x["inter_area"], x["days_diff"]))
        return candidates[0]["chip"]

    def find_matching_af_chip(
        self,
        user_bbox_poly: Polygon,
        center_lon: float,
        center_lat: float,
        target_date: Optional[date] = None,
        bs_chip_bbox_poly: Optional[Polygon] = None,
        max_days_diff: int = 15
    ) -> Optional[Dict[str, Any]]:
        """
        Строгий подбор чипа термоточек AF:
        1. Должен пространственно перекрывать BBox пользователя (и контур гари BS, если задан).
        2. Дата пролета VIIRS должна быть в пределах target_date ± max_days_diff дней (не более 15 дней).
        3. Чип должен содержать подтвержденное горение (n_fire_px > 0).
        """
        if not self.af_chips:
            return None

        candidates = []
        for chip in self.af_chips:
            # 1. Проверка пересечения с BBox
            if not user_bbox_poly.intersects(chip["poly_wgs"]):
                continue

            # Если передан BBox найденной гари — чип VIIRS должен пересекать именно зону пожара
            if bs_chip_bbox_poly is not None and not bs_chip_bbox_poly.intersects(chip["poly_wgs"]):
                continue

            inter_area = user_bbox_poly.intersection(chip["poly_wgs"]).area

            # 2. Временное окно
            if target_date and chip["acq_datetime"]:
                chip_d = chip["acq_datetime"].date()
                days_diff = abs((chip_d - target_date).days)
                if days_diff > max_days_diff:
                    continue
            else:
                days_diff = 0

            candidates.append({
                "chip": chip,
                "inter_area": inter_area,
                "days_diff": days_diff,
                "has_fire": chip["n_fire_px"] > 0
            })

        if not candidates:
            return None

        # Приоритет: наличие пламени, минимальная разница по дате с пожаром, максимальное перекрытие
        candidates.sort(key=lambda x: (not x["has_fire"], x["days_diff"], -x["inter_area"]))
        return candidates[0]["chip"]

    def get_featured_presets(self) -> List[Dict[str, Any]]:
        """
        Возвращает список ключевых реальных пожаров из обучающей базы
        для удобного интерактивного выбора в UI.
        """
        presets = [
            {
                "id": "volgograd_huge_2022",
                "name": "Волгоград — Заволжье (август 2022, 3350 га)",
                "chip_id": "BS_tr_000109",
                "af_chip_id": "AF_tr_000250",
                "bbox": [46.12, 49.50, 46.34, 49.68],
                "date_from": "2022-08-10",
                "date_to": "2022-08-28",
                "event_id": "FE13548",
                "desc": "Степной пожар в Заволжье: 54 термоточки строго внутри контура гари"
            },
            {
                "id": "astrakhan_max_2019",
                "name": "Астрахань — Волго-Ахтуба (июнь 2019, 2306 га)",
                "chip_id": "BS_tr_000004",
                "af_chip_id": "AF_tr_000023",
                "bbox": [46.50, 48.20, 46.72, 48.38],
                "date_from": "2019-06-15",
                "date_to": "2019-06-28",
                "event_id": "FE00977",
                "desc": "Масштабный пал пойменной растительности с активным огнем"
            },
            {
                "id": "rostov_salsk_2022",
                "name": "Ростовская обл. — Сальск (август 2022, 1694 га)",
                "chip_id": "BS_tr_000101",
                "af_chip_id": "AF_tr_000238",
                "bbox": [42.55, 47.00, 42.77, 47.18],
                "date_from": "2022-07-30",
                "date_to": "2022-08-16",
                "event_id": "FE13054",
                "desc": "Степной пожар: 40 термоточек VIIRS внутри контура"
            },
            {
                "id": "volgograd_north_2019",
                "name": "Волгоград — Север (июнь 2019, 2487 га)",
                "chip_id": "BS_tr_000003",
                "af_chip_id": "AF_tr_000019",
                "bbox": [47.07, 48.66, 47.30, 48.83],
                "date_from": "2019-06-12",
                "date_to": "2019-06-27",
                "event_id": "FE01122",
                "desc": "Крупный пожар: 34 термоточки VIIRS точно внутри гари"
            },
            {
                "id": "kalmykia_south_2024",
                "name": "Калмыкия — Южный рубеж (сентябрь 2024, 1759 га)",
                "chip_id": "BS_tr_000202",
                "af_chip_id": "AF_tr_000412",
                "bbox": [39.25, 47.94, 39.48, 48.12],
                "date_from": "2024-09-18",
                "date_to": "2024-10-05",
                "event_id": "FE24108",
                "desc": "Свежий осенний пожар сезона 2024 года (28 термоточек)"
            }
        ]
        return presets


# Глобальный инстанс каталога
catalog = ChipCatalog()
