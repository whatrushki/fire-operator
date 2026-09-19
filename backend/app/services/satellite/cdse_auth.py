"""
Менеджер аутентификации OAuth2 для Copernicus Data Space Ecosystem (CDSE).
Обеспечивает получение и автоматическое обновление Bearer-токенов
для доступа к OData каталогу и Sentinel Hub Process API.
"""

import time
import threading
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class CDSEAuthManager:
    """
    Потокобезопасный менеджер токенов OAuth2 для Copernicus Data Space Ecosystem.
    Документация: https://dataspace.copernicus.eu/analyse/apis/token
    """

    TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        timeout_sec: float = 10.0
    ):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.timeout_sec = timeout_sec

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        """Проверяет наличие client_id и client_secret."""
        return bool(self.client_id and self.client_secret)

    def get_access_token(self) -> Optional[str]:
        """
        Возвращает валидный Bearer access token.
        Если токен отсутствует или истекает в течение 60 секунд, выполняется обновление.
        """
        if not self.is_configured():
            logger.warning("[CDSEAuth] CDSE_CLIENT_ID или CDSE_CLIENT_SECRET не настроены.")
            return None

        with self._lock:
            now = time.time()
            if self._access_token and (now < self._expires_at - 60):
                return self._access_token

            # Запрос нового токена
            try:
                logger.info("[CDSEAuth] Запрос обновления OAuth2 токена CDSE...")
                data = {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded"
                }

                with httpx.Client(timeout=self.timeout_sec) as client:
                    resp = client.post(self.TOKEN_URL, data=data, headers=headers)

                    if resp.status_code != 200:
                        logger.error("[CDSEAuth] Ошибка авторизации CDSE (HTTP %d): %s", resp.status_code, resp.text[:200])
                        return None

                    payload = resp.json()
                    self._access_token = payload.get("access_token")
                    expires_in = float(payload.get("expires_in", 600))
                    self._expires_at = now + expires_in
                    logger.info("[CDSEAuth] Токен CDSE успешно получен (TTL: %.0f сек).", expires_in)
                    return self._access_token

            except Exception as exc:
                logger.error("[CDSEAuth] Сбой сетевого запроса токена CDSE: %s", exc)
                return None
