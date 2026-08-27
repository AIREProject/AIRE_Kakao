import asyncio
import logging
import time
from hmac import compare_digest
from typing import Protocol
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api_client import AireApiClient, BackendResponseError
from config import (
    BACKEND_URL,
    COMPANION_ID,
    KAKAO_ADAPTER_TOKEN,
    KAKAO_SKILL_SECRET,
    PORT,
    SAVE_SLOT_ID,
)

KAKAO_SKILL_SECRET_HEADER = "X-Kakao-Skill-Secret"
KAKAO_SIMPLE_TEXT_MAX_LENGTH = 1000
DIRECT_RESPONSE_TIMEOUT_SECONDS = 4.0
START_TIME = time.time()

logger = logging.getLogger("aire.kakao")


class ChatClient(Protocol):
    async def send_chat(
        self,
        user_message: str,
        *,
        bot_id: str,
        user_id: str,
        user_type: str,
    ) -> str: ...


class KakaoInputModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, populate_by_name=True)


class KakaoUser(KakaoInputModel):
    id: str = Field(min_length=1, max_length=70)
    type: str = Field(min_length=1, max_length=32)


class KakaoBot(KakaoInputModel):
    id: str = Field(min_length=1, max_length=70)


class KakaoUserRequest(KakaoInputModel):
    utterance: str = Field(min_length=1, max_length=2000)
    user: KakaoUser
    callback_url: str | None = Field(default=None, alias="callbackUrl", max_length=2048)


class KakaoSkillPayload(KakaoInputModel):
    bot: KakaoBot
    user_request: KakaoUserRequest = Field(alias="userRequest")


def _simple_text(text: str) -> dict[str, object]:
    normalized = text.strip()
    if not normalized:
        normalized = "지금은 답을 만들지 못했어. 잠시 뒤에 다시 말해 줘."
    if len(normalized) > KAKAO_SIMPLE_TEXT_MAX_LENGTH:
        normalized = f"{normalized[:997]}..."
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": normalized}}]},
    }


def _validate_callback_url(callback_url: str) -> None:
    parsed = urlsplit(callback_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(status_code=400, detail="Invalid Kakao callback URL.")


async def _post_callback(callback_url: str, payload: dict[str, object]) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(callback_url, json=payload)
        response.raise_for_status()


async def _safe_chat(
    client: ChatClient,
    utterance: str,
    *,
    bot_id: str,
    user_id: str,
    user_type: str,
) -> dict[str, object]:
    try:
        return _simple_text(
            await client.send_chat(
                utterance,
                bot_id=bot_id,
                user_id=user_id,
                user_type=user_type,
            )
        )
    except (BackendResponseError, httpx.HTTPError, TimeoutError, ValueError):
        return _simple_text("지금은 대화 연결이 불안정해. 잠시 뒤에 다시 말해 줘.")


async def _respond_via_callback(
    client: ChatClient,
    utterance: str,
    callback_url: str,
    bot_id: str,
    user_id: str,
    user_type: str,
) -> None:
    response = await _safe_chat(
        client,
        utterance,
        bot_id=bot_id,
        user_id=user_id,
        user_type=user_type,
    )
    try:
        await _post_callback(callback_url, response)
    except httpx.HTTPError:
        logger.warning("kakao_callback_delivery_failed")


def create_app(
    *,
    chat_client: ChatClient | None = None,
    skill_secret: str = KAKAO_SKILL_SECRET,
    direct_timeout_seconds: float = DIRECT_RESPONSE_TIMEOUT_SECONDS,
) -> FastAPI:
    selected_client = chat_client or AireApiClient()
    app = FastAPI(title="AIRE KakaoTalk Bot")

    @app.api_route("/", methods=["GET", "HEAD"])
    @app.api_route("/health", methods=["GET", "HEAD"])
    async def health_check() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "AIRE_Kakao",
            "backend_url": BACKEND_URL,
            "save_slot_id": SAVE_SLOT_ID,
            "companion_id": COMPANION_ID,
            "skill_configured": bool(skill_secret),
            "uptime_seconds": round(time.time() - START_TIME, 2),
        }

    @app.post("/kakao/skill")
    async def handle_skill(
        payload: KakaoSkillPayload,
        background_tasks: BackgroundTasks,
        x_kakao_skill_secret: str | None = Header(
            default=None,
            alias=KAKAO_SKILL_SECRET_HEADER,
            max_length=256,
        ),
    ) -> dict[str, object]:
        if not skill_secret:
            raise HTTPException(status_code=503, detail="Kakao skill is not configured.")
        if x_kakao_skill_secret is None or not compare_digest(
            x_kakao_skill_secret, skill_secret
        ):
            raise HTTPException(status_code=401, detail="Invalid Kakao skill secret.")
        if chat_client is None and not KAKAO_ADAPTER_TOKEN:
            raise HTTPException(status_code=503, detail="Kakao adapter is not configured.")

        user = payload.user_request.user
        if user.type != "botUserKey":
            raise HTTPException(status_code=400, detail="Unsupported Kakao user type.")
        bot_id = payload.bot.id

        callback_url = payload.user_request.callback_url
        if callback_url is not None:
            _validate_callback_url(callback_url)
            background_tasks.add_task(
                _respond_via_callback,
                selected_client,
                payload.user_request.utterance,
                callback_url,
                bot_id,
                user.id,
                user.type,
            )
            return {"version": "2.0", "useCallback": True}

        try:
            async with asyncio.timeout(direct_timeout_seconds):
                return await _safe_chat(
                    selected_client,
                    payload.user_request.utterance,
                    bot_id=bot_id,
                    user_id=user.id,
                    user_type=user.type,
                )
        except TimeoutError:
            return _simple_text("지금은 대화 연결이 불안정해. 잠시 뒤에 다시 말해 줘.")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
