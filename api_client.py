"""Kakao 사용자 문맥을 AIRE Backend의 모바일 대화 요청으로 변환합니다.

Adapter는 원본 botUserKey를 저장하지 않고 Backend 요청 경계까지만 전달합니다.
Backend는 bot.id와 botUserKey로 채널 전용 HMAC Profile을 복원하므로 Kakao 기억은
게임·웹 Profile과 섞이지 않습니다. 응답은 Request ID로 상관관계를 검증하고,
사용자 발화를 그대로 되풀이한 문장은 안전한 MAKO 응답으로 교체합니다.
"""

import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

from config import (
    API_TIMEOUT_SECONDS,
    BACKEND_URL,
    KAKAO_ADAPTER_TOKEN,
    COMPANION_ID,
    SAVE_SLOT_ID,
)

KST = timezone(timedelta(hours=9))
KAKAO_SESSION_ID = "kakao"

_ROLE_WRAPPER_PATTERN = re.compile(
    r"^(?:(?:사용자|유저|플레이어|사람|user|human|player)\s*[:：-]\s*|"
    r"(?:네가|사용자가|유저가|플레이어가)\s*(?:말한|보낸)\s*"
    r"(?:말|내용|문장)?\s*[:：-]\s*)",
    re.IGNORECASE,
)
_SHORT_ACKNOWLEDGEMENTS = ("응", "그래", "맞아", "어")
_SAFE_DISPLAY_TEXTS = (
    "응, 그 얘기 조금만 더 들려줘. 네 생각을 제대로 알고 싶어.",
    "그래, 어디부터 같이 얘기해 볼까?",
    "마코는 여기 있어. 편하게 이어서 말해 줘.",
)


class BackendResponseError(RuntimeError):
    pass


def _normalize_echo_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(text)).lower()
    for _ in range(3):
        unwrapped = _ROLE_WRAPPER_PATTERN.sub("", normalized)
        if unwrapped == normalized:
            break
        normalized = unwrapped
    return "".join(character for character in normalized if character.isalnum())


def _is_player_echo(display_text: str, user_message: str) -> bool:
    normalized_response = _normalize_echo_text(display_text)
    normalized_user = _normalize_echo_text(user_message)
    if not normalized_response or not normalized_user:
        return False
    if normalized_response == normalized_user:
        return True
    if (
        len(normalized_user) >= 2
        and normalized_user in normalized_response
        and len(normalized_response) - len(normalized_user) <= 12
    ):
        return True
    if any(
        normalized_response == f"{acknowledgement}{normalized_user}"
        for acknowledgement in _SHORT_ACKNOWLEDGEMENTS
    ):
        return True
    slash_variants = [
        _normalize_echo_text(variant)
        for variant in display_text.split("/")
        if _normalize_echo_text(variant)
    ]
    return len(slash_variants) > 1 and all(
        variant == normalized_user for variant in slash_variants
    )


def _guard_display_text(display_text: str, user_message: str) -> str:
    if not _is_player_echo(display_text, user_message):
        return display_text
    for fallback in _SAFE_DISPLAY_TEXTS:
        if not _is_player_echo(fallback, user_message):
            return fallback
    return "잠깐만, 네 얘기를 다시 생각해 볼게."


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
    """Kakao Identity와 대화 Context를 AIRE 통합 API 계약에 맞추는 Client입니다."""

    def __init__(
        self,
        *,
        base_url: str = BACKEND_URL,
        adapter_token: str = KAKAO_ADAPTER_TOKEN,
        timeout_seconds: float = API_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._adapter_token = adapter_token
        self._timeout_seconds = timeout_seconds

    async def send_chat(
        self,
        user_message: str,
        *,
        bot_id: str,
        user_id: str,
        user_type: str,
    ) -> str:
        now = datetime.now(KST)
        request_id = f"kakao-{uuid4()}"
        payload = {
            "schema_version": 1,
            "request_id": request_id,
            "session_id": KAKAO_SESSION_ID,
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
        chat_request = payload
        payload = {
            "bot_id": bot_id,
            "user": {"id": user_id, "type": user_type},
            "chat": chat_request,
        }
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._adapter_token}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/api/v1/integrations/kakao/chat",
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
        return _guard_display_text(display_text, user_message)
