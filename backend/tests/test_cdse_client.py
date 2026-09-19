"""
Тесты для Copernicus CDSE OAuth2 авторизации и клиента каталога (app.services.satellite.cdse_*).
"""

from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from app.services.satellite.cdse_auth import CDSEAuthManager
from app.services.satellite.cdse_client import CDSEClient


def test_cdse_auth_unconfigured():
    auth = CDSEAuthManager(client_id="", client_secret="")
    assert not auth.is_configured()
    token = auth.get_access_token()
    assert token is None


def test_cdse_auth_token_fetch_and_cache():
    auth = CDSEAuthManager(client_id="my_id", client_secret="my_secret")
    assert auth.is_configured()

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "mock_jwt_token_abc_123",
            "expires_in": 600
        }
        mock_post.return_value = mock_resp

        token1 = auth.get_access_token()
        assert token1 == "mock_jwt_token_abc_123"
        assert mock_post.call_count == 1

        # Повторный вызов использует кэшированный токен без повторного запроса
        token2 = auth.get_access_token()
        assert token2 == "mock_jwt_token_abc_123"
        assert mock_post.call_count == 1


def test_cdse_client_search_scenes():
    auth = CDSEAuthManager(client_id="id", client_secret="sec")
    client = CDSEClient(auth=auth)

    odata_mock_response = {
        "value": [
            {
                "Id": "scene_001",
                "Name": "S2B_MSIL2A_20240815T082559_N0510_R107_T38UMU_20240815T121500.SAFE",
                "ContentDate": {"Start": "2024-08-15T08:25:59.000Z"},
                "Attributes": [
                    {"Name": "cloudCover", "Value": 12.4}
                ]
            }
        ]
    }

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = odata_mock_response
        mock_get.return_value = mock_resp

        scenes = client.search_scenes(
            bbox=(43.0, 47.0, 45.5, 48.5),
            date_from=date(2024, 8, 1),
            date_to=date(2024, 8, 20),
            collection="SENTINEL-2",
            max_cloud_cover=30.0
        )

        assert len(scenes) == 1
        assert scenes[0]["id"] == "scene_001"
        assert scenes[0]["cloud_cover"] == 12.4
        assert scenes[0]["collection"] == "SENTINEL-2"
