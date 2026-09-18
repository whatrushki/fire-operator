"""
Геопространственные сервисы: расчет зон UTM, площадей в гектарах и векторизация растров.
"""
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import transform
import pyproj

from app.core.config import settings


def get_utm_epsg_from_lon(lon: float) -> int:
    """Определяет код EPSG зоны UTM для заданной долготы (Северное полушарие)."""
    zone = int(np.floor((lon + 180) / 6)) + 1
    return 32600 + zone


def vectorize_burn_mask(
    mask: np.ndarray,
    transform_matrix: rasterio.Affine,
    src_crs: str = "EPSG:32638",
    dst_crs: str = "EPSG:4326",
    simplify_tol_m: float = 2.0
) -> list[dict]:
    """
    Векторизует растровую маску гарей (значения 1, 2, 3) в GeoJSON фичи WGS84.
    
    Args:
        mask: 2D uint8 array (512, 512) со значениями 0, 1, 2, 3.
        transform_matrix: аффинное преобразование растра.
        src_crs: исходная система координат (UTM).
        dst_crs: целевая система координат (WGS84).
        simplify_tol_m: допуск упрощения Дугласа-Пекера в метрах.
        
    Returns:
        Список GeoJSON Feature словарей.
    """
    project = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True).transform
    features = []
    contour_idx = 1
    
    severity_labels = {
        1: ("Слабая", "Low"),
        2: ("Средняя", "Moderate"),
        3: ("Сильная", "High")
    }
    
    # Итерируемся по классам гари
    for cls_id in (1, 2, 3):
        cls_mask = (mask == cls_id).astype(np.uint8)
        if not np.any(cls_mask):
            continue
            
        # Генерация полигонов из маски
        for geom_dict, val in shapes(cls_mask, mask=(cls_mask == 1), transform=transform_matrix):
            if val != 1:
                continue
                
            poly = shape(geom_dict)
            if poly.is_empty or poly.area < 400.0:  # отсекаем полигоны меньше 1 пикселя
                continue
                
            # Упрощение геометрии для оптимизации размера
            if simplify_tol_m > 0:
                poly = poly.simplify(simplify_tol_m, preserve_topology=True)
                
            area_m2 = poly.area
            area_ha = round(area_m2 / 10000.0, 3)
            
            # Перевод в WGS84 для отображения на веб-карте
            poly_wgs84 = transform(project, poly)
            
            label_ru, label_en = severity_labels[cls_id]
            
            feature = {
                "type": "Feature",
                "id": f"BS-CNT-{contour_idx:04d}",
                "geometry": mapping(poly_wgs84),
                "properties": {
                    "contour_id": f"BS-CNT-{contour_idx:04d}",
                    "severity_class": cls_id,
                    "severity_ru": label_ru,
                    "severity_en": label_en,
                    "area_ha": area_ha,
                    "utm_zone": src_crs
                }
            }
            features.append(feature)
            contour_idx += 1
            
    return features


def calculate_area_breakdown(mask: np.ndarray, pixel_area_ha: float = 0.04) -> tuple[float, list[dict]]:
    """
    Рассчитывает суммарную площадь и поклассовую разбивку в гектарах.
    """
    total_px = int(np.sum(mask > 0))
    total_area_ha = round(total_px * pixel_area_ha, 2)
    
    breakdown = []
    names = {
        1: "Слабая степень (Low)",
        2: "Средняя степень (Moderate)",
        3: "Сильная степень (High)"
    }
    
    for cls_id in (1, 2, 3):
        px_count = int(np.sum(mask == cls_id))
        area_ha = round(px_count * pixel_area_ha, 2)
        pct = round((area_ha / total_area_ha * 100.0) if total_area_ha > 0 else 0.0, 1)
        breakdown.append({
            "class_id": cls_id,
            "name": names[cls_id],
            "area_ha": area_ha,
            "percentage": pct
        })
        
    return total_area_ha, breakdown
