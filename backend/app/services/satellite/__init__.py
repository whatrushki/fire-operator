"""
Модуль интеграции с онлайн-спутниками для Fire-Operator.
Обеспечивает доступ к оперативным данным NASA FIRMS (VIIRS NRT)
и мультиспектральным снимкам Copernicus CDSE (Sentinel-2 / Sentinel-1 SAR).
"""

from app.services.satellite.provider import (
    DataSourceType,
    SatelliteDataProvider,
    get_satellite_provider,
)
from app.services.satellite.firms_client import FIRMSClient
from app.services.satellite.cdse_auth import CDSEAuthManager
from app.services.satellite.cdse_client import CDSEClient
from app.services.satellite.cache import SceneCache

__all__ = [
    "DataSourceType",
    "SatelliteDataProvider",
    "get_satellite_provider",
    "FIRMSClient",
    "CDSEAuthManager",
    "CDSEClient",
    "SceneCache",
]
