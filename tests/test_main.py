import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import create_app

SECRET = "test-kakao-secret"


class FakeChatClient:
    def __init__(self, text: str = "안녕. 오늘도 같이 가자.") -> None:
        self.text = text
        self.messages: list[dict[str, str]] = []

    async def send_chat(
        self,
        user_message: str,
        *,
        bot_id: str,
        user_id: str,
        user_type: str,
    ) -> str:
        self.messages.append(
            {
                "message": user_message,
                "bot_id": bot_id,
                "user_id": user_id,
                "user_type": user_type,
            }
        )
        return self.text


def _payload(user_id: str = "user-1", **overrides: Any) -> dict[str, Any]:
    user_request: dict[str, Any] = {
        "utterance": "안녕",
        "user": {"id": user_id, "type": "botUserKey", "ignored": "ok"},
        "timezone": "Asia/Seoul",
    }
    user_request.update(overrides)
    return {"userRequest": user_request, "bot": {"id": "bot-1"}}


def _client(fake: FakeChatClient, timeout: float = 4.0) -> TestClient:
    return TestClient(
        create_app(
            chat_client=fake,
            skill_secret=SECRET,
            direct_timeout_seconds=timeout,
        )
    )


class KakaoSkillTests(unittest.TestCase):
    def test_channel_users_forward_distinct_identities(self) -> None:
        fake = FakeChatClient()
        client = _client(fake)

        first = client.post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload("user-a"),
        )
        second = client.post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload("user-b"),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            fake.messages,
            [
                {
                    "message": "안녕",
                    "bot_id": "bot-1",
                    "user_id": "user-a",
                    "user_type": "botUserKey",
                },
                {
                    "message": "안녕",
                    "bot_id": "bot-1",
                    "user_id": "user-b",
                    "user_type": "botUserKey",
                },
            ],
        )

    def test_unsupported_user_type_is_rejected(self) -> None:
        response = _client(FakeChatClient()).post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json={
                **_payload(),
                "userRequest": {
                    **_payload()["userRequest"],
                    "user": {"id": "user-1", "type": "id"},
                },
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_missing_or_invalid_secret_is_rejected(self) -> None:
        client = _client(FakeChatClient())

        self.assertEqual(client.post("/kakao/skill", json=_payload()).status_code, 401)
        self.assertEqual(
            client.post(
                "/kakao/skill",
                headers={"X-Kakao-Skill-Secret": "wrong"},
                json=_payload(),
            ).status_code,
            401,
        )

    def test_unconfigured_skill_is_unavailable(self) -> None:
        response = TestClient(
            create_app(chat_client=FakeChatClient(), skill_secret="")
        ).post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload(),
        )

        self.assertEqual(response.status_code, 503)

    def test_missing_adapter_token_is_unavailable(self) -> None:
        response = TestClient(create_app(skill_secret=SECRET)).post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload(),
        )

        self.assertEqual(response.status_code, 503)

    def test_direct_timeout_returns_valid_fallback(self) -> None:
        class SlowChatClient(FakeChatClient):
            async def send_chat(
                self,
                user_message: str,
                *,
                bot_id: str,
                user_id: str,
                user_type: str,
            ) -> str:
                await asyncio.sleep(0.05)
                return await super().send_chat(
                    user_message,
                    bot_id=bot_id,
                    user_id=user_id,
                    user_type=user_type,
                )

        response = _client(SlowChatClient(), timeout=0.001).post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload(),
        )

        self.assertEqual(response.status_code, 200)
        text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
        self.assertIn("연결이 불안정", text)

    def test_callback_returns_pending_and_delivers_response(self) -> None:
        fake = FakeChatClient()
        with patch("main._post_callback", new=AsyncMock()) as post_callback:
            response = _client(fake).post(
                "/kakao/skill",
                headers={"X-Kakao-Skill-Secret": SECRET},
                json=_payload(callbackUrl="https://callback.example/kakao"),
            )

        self.assertEqual(response.json(), {"version": "2.0", "useCallback": True})
        post_callback.assert_awaited_once()
        self.assertEqual(
            fake.messages,
            [
                {
                    "message": "안녕",
                    "bot_id": "bot-1",
                    "user_id": "user-1",
                    "user_type": "botUserKey",
                }
            ],
        )

    def test_invalid_callback_url_is_rejected(self) -> None:
        response = _client(FakeChatClient()).post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload(callbackUrl="http://127.0.0.1/internal"),
        )

        self.assertEqual(response.status_code, 400)

    def test_text_is_bounded_to_kakao_limit(self) -> None:
        response = _client(FakeChatClient("가" * 1200)).post(
            "/kakao/skill",
            headers={"X-Kakao-Skill-Secret": SECRET},
            json=_payload(),
        )

        text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
        self.assertEqual(len(text), 1000)
        self.assertTrue(text.endswith("..."))


if __name__ == "__main__":
    unittest.main()
