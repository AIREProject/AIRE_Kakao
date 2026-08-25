from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

from config import (
    API_TIMEOUT_SECONDS,
    BACKEND_URL,
    BEARER_TOKEN,
    COMPANION_ID,
    SAVE_SLOT_ID,
)

KST = timezone(timedelta(hours=9))
KAKAO_SHARED_SESSION_ID = "kakao-shared"


class BackendResponseError(RuntimeError):
    pass


def _period_for_hour(hour: int) -> str:
    if 5 <= hour < 8:
        return "Dawn"
    if 8 <= hour < 12:
        return "Morning"
    if 12 <= hour < 14:
        return "Noon"
    if 14 <= hour < 18:
        return "Afternoon"
    if 18 <= hour < 22:
        return "Evening"
    if hour == 0 or hour >= 22:
        return "Midnight"
    return "Night"


class AireApiClient:
    def __init__(
        self,
        *,
        base_url: str = BACKEND_URL,
        bearer_token: str = BEARER_TOKEN,
        timeout_seconds: float = API_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds

    async def send_chat(self, user_message: str) -> str:
        now = datetime.now(KST)
        request_id = f"kakao-{uuid4()}"
        payload = {
            "schema_version": 1,
            "request_id": request_id,
            "session_id": KAKAO_SHARED_SESSION_ID,
            "save_slot_id": SAVE_SLOT_ID,
            "companion_id": COMPANION_ID,
            "message_id": f"message-{uuid4()}",
            "user_message": user_message,
            "surface": "mobile",
            "time_context": {
                "source": "RealWorld",
                "day": now.day,
                "hour": now.hour,
                "period": _period_for_hour(now.hour),
            },
            "allowed_commands": [],
        }
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._bearer_token}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/api/v1/chat",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data: Any = response.json()

        if not isinstance(data, dict) or data.get("request_id") != request_id:
            raise BackendResponseError("Backend response correlation failed.")
        display_text = data.get("display_text")
        if not isinstance(display_text, str) or not display_text.strip():
            raise BackendResponseError("Backend response is missing display_text.")
        return display_text
