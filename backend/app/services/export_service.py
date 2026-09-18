"""
Сервис экспорта аналитических данных: GeoJSON, Shapefile ZIP и справок.
"""
import os
import json
import zipfile
import tempfile
import geopandas as gpd
from shapely.geometry import shape

from app.core.config import settings


def export_geojson(features: list[dict], out_path: str) -> str:
    """Сохраняет список Feature в файл GeoJSON (RFC 7946, UTF-8)."""
    geojson_dict = {
        "type": "FeatureCollection",
        "features": features
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, ensure_ascii=False, indent=2)
    return out_path


def export_shapefile_zip(features: list[dict], zip_out_path: str) -> str:
    """
    Конвертирует список Feature в ESRI Shapefile и упаковывает в ZIP архив
    со всеми необходимыми файлами (.shp, .shx, .dbf, .prj, .cpg).
    """
    if not features:
        # Если пусто, создаем пустой zip
        with zipfile.ZipFile(zip_out_path, "w") as zf:
            zf.writestr("README.txt", "No burned area features detected for requested query.")
        return zip_out_path

    # Преобразуем GeoJSON фичи в GeoDataFrame
    records = []
    geometries = []
    for f in features:
        geom = shape(f["geometry"])
        props = f["properties"].copy()
        records.append(props)
        geometries.append(geom)

    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")

    with tempfile.TemporaryDirectory() as tmp_dir:
        shp_name = "fire_burn_contours"
        shp_path = os.path.join(tmp_dir, f"{shp_name}.shp")
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")

        # Принудительно создаем .cpg для корректного отображения кириллицы в QGIS/ArcGIS
        cpg_path = os.path.join(tmp_dir, f"{shp_name}.cpg")
        with open(cpg_path, "w", encoding="utf-8") as cpg_f:
            cpg_f.write("UTF-8")

        # Упаковка всех сгенерированных файлов в ZIP
        with zipfile.ZipFile(zip_out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(tmp_dir):
                fpath = os.path.join(tmp_dir, fname)
                zf.write(fpath, arcname=fname)

    return zip_out_path
