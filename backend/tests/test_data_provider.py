"""
Тесты для SatelliteDataProvider и API эндпоинта /satellites/status.
"""

from datetime import date
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.satellite.provider import (
    DataSourceType,
    SatelliteDataProvider,
    get_satellite_provider
)


client = TestClient(app)


def test_provider_offline_mode():
    provider = SatelliteDataProvider(mode="offline")
    assert provider.mode == DataSourceType.OFFLINE
    assert not provider.is_online_enabled()

    pts, tag, meta = provider.get_thermal_points(
        bbox=(43.0, 47.0, 45.0, 48.0),
        date_from=date(2024, 8, 1),
        date_to=date(2024, 8, 10)
    )
    assert pts is None  # Signals caller to use local catalog
    assert tag == "offline"


def test_provider_hybrid_fallback_when_unconfigured():
    provider = SatelliteDataProvider(mode="hybrid")
    assert provider.mode == DataSourceType.HYBRID
    assert provider.is_online_enabled()

    # Если FIRMS не настроен, гибридный режим прозрачно делает fallback
    pts, tag, meta = provider.get_thermal_points(
        bbox=(43.0, 47.0, 45.0, 48.0),
        date_from=date(2024, 8, 1),
        date_to=date(2024, 8, 10)
    )
    assert pts is None
    assert tag == "offline_fallback"


def test_provider_online_with_mock_firms():
    provider = SatelliteDataProvider(mode="online")
    mock_pts = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [44.5, 48.2]},
            "properties": {"satellite": "VIIRS", "confidence": "high"}
        }
    ]

    with patch.object(provider.firms, "is_configured", return_value=True):
        with patch.object(provider.firms, "fetch_active_fires", return_value=mock_pts):
            pts, tag, meta = provider.get_thermal_points(
                bbox=(43.0, 47.0, 45.0, 48.0),
                date_from=date(2024, 8, 1),
                date_to=date(2024, 8, 10)
            )
            assert pts == mock_pts
            assert tag == "online_firms"
            assert meta["count"] == 1


def test_api_satellites_status():
    resp = client.get("/api/v1/satellites/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data
    assert "firms" in data
    assert "cdse" in data
    assert "cache" in data
    assert data["firms"]["service"].startswith("NASA FIRMS")


def test_api_analyze_with_data_source_flag():
    payload = {
        "region": "volgograd",
        "date_from": "2024-06-01",
        "date_to": "2024-08-30",
        "include_radar": True,
        "data_source": "offline"
    }
    resp = client.post("/api/v1/analyze", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data
