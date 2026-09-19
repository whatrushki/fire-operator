"""
Тесты для клиента NASA FIRMS API (app.services.satellite.firms_client).
"""

from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from app.services.satellite.cache import SceneCache
from app.services.satellite.firms_client import FIRMSClient


MOCK_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
48.125,44.567,335.2,0.39,0.36,2024-08-15,0930,Suomi-NPP,nominal,2.0NRT,295.1,12.5,D
48.200,44.700,355.0,0.40,0.37,2024-08-15,0930,NOAA-20,high,2.0NRT,300.0,28.4,D
49.500,44.500,310.0,0.39,0.36,2024-08-15,0930,Suomi-NPP,low,2.0NRT,298.0,3.1,D
55.000,60.000,340.0,0.40,0.37,2024-08-15,0930,Suomi-NPP,high,2.0NRT,295.0,15.0,D
"""


def test_firms_client_unconfigured():
    client = FIRMSClient(api_key="")
    assert not client.is_configured()
    points = client.fetch_active_fires(
        bbox=(43.0, 47.0, 46.0, 49.0),
        date_from=date(2024, 8, 1),
        date_to=date(2024, 8, 15)
    )
    assert points == []


def test_firms_client_parse_and_filter(tmp_path):
    cache = SceneCache(cache_dir=str(tmp_path / "cache"), ttl_hours=1)
    client = FIRMSClient(api_key="test_map_key_123", cache=cache)
    assert client.is_configured()

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = MOCK_FIRMS_CSV
        mock_get.return_value = mock_resp

        bbox = (43.0, 47.0, 46.0, 49.0)
        points = client.fetch_active_fires(
            bbox=bbox,
            date_from=date(2024, 8, 10),
            date_to=date(2024, 8, 15),
            min_confidence="nominal"
        )

        assert len(points) == 2  # 1 out of bbox, 1 low confidence filtered out
        p1 = points[0]
        assert p1["type"] == "Feature"
        assert p1["geometry"]["coordinates"] == [44.567, 48.125]
        assert p1["properties"]["confidence"] == "nominal"
        assert p1["properties"]["frp"] == 12.5
        assert p1["properties"]["brightness_temp_i4_k"] == 335.2
        assert p1["properties"]["delta_t_k"] == 40.1

        p2 = points[1]
        assert p2["properties"]["confidence"] == "high"
        assert p2["properties"]["satellite"] == "NOAA-20"

        # Проверка кэширования: повторный вызов не должен делать сетевой запрос
        mock_get.reset_mock()
        cached_points = client.fetch_active_fires(
            bbox=bbox,
            date_from=date(2024, 8, 10),
            date_to=date(2024, 8, 15),
            min_confidence="nominal"
        )
        assert len(cached_points) == 2
        mock_get.assert_not_called()


def test_firms_client_network_error():
    client = FIRMSClient(api_key="valid_key")
    with patch("httpx.Client.get", side_effect=Exception("Connection timed out")):
        points = client.fetch_active_fires(
            bbox=(43.0, 47.0, 46.0, 49.0),
            date_from=date(2024, 8, 1),
            date_to=date(2024, 8, 5)
        )
        assert points == []
