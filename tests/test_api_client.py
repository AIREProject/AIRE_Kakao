import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from api_client import AireApiClient, _guard_display_text


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"request_id": self.request_id, "display_text": "반가워."}


class FakeAsyncClient:
    last_request: dict[str, Any] | None = None

    def __init__(self, **_: Any) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
        self.last_request = {"url": url, "headers": headers, "json": json}
        FakeAsyncClient.last_request = self.last_request
        response = FakeResponse()
        response.request_id = json["chat"]["request_id"]
        return response


class AireApiClientTests(unittest.TestCase):
    def test_display_guard_replaces_exact_and_wrapped_player_echoes(self) -> None:
        player_text = "나는 민트초코를 좋아해."

        for response_text in (
            player_text,
            '사용자: "나는 민트초코를 좋아해."',
            "응, 나는 민트초코를 좋아해.",
            "나는 민트초코를 좋아해 / 나는 민트초코를 좋아해",
        ):
            with self.subTest(response_text=response_text):
                guarded = _guard_display_text(response_text, player_text)
                self.assertNotEqual(guarded, response_text)
                self.assertNotIn("민트초코", guarded)

    def test_display_guard_preserves_contextual_memory_response(self) -> None:
        response_text = "네가 민트초코를 좋아한다고 기억하고 있어."

        self.assertEqual(
            _guard_display_text(response_text, "내가 좋아하는 음식이 뭐였지?"),
            response_text,
        )

    def test_kakao_wrapper_preserves_identity_and_mobile_chat_shape(self) -> None:
        async def run() -> str:
            client = AireApiClient(
                base_url="https://backend.example",
                adapter_token="adapter-secret",
            )
            return await client.send_chat(
                "안녕",
                bot_id="bot-7",
                user_id="user-9",
                user_type="botUserKey",
            )

        with patch("api_client.httpx.AsyncClient", FakeAsyncClient):
            self.assertEqual(asyncio.run(run()), "반가워.")

        request = FakeAsyncClient.last_request
        assert request is not None
        self.assertEqual(request["url"], "https://backend.example/api/v1/integrations/kakao/chat")
        self.assertEqual(request["headers"]["Authorization"], "Bearer adapter-secret")
        self.assertEqual(
            request["json"]["user"],
            {"id": "user-9", "type": "botUserKey"},
        )
        self.assertEqual(request["json"]["bot_id"], "bot-7")
        chat = request["json"]["chat"]
        self.assertEqual(chat["session_id"], "kakao")
        self.assertEqual(chat["surface"], "mobile")
        self.assertEqual(chat["save_slot_id"], "demo-slot-1")
        self.assertEqual(chat["companion_id"], "mako")
        self.assertEqual(chat["allowed_commands"], [])
        self.assertNotIn("game_context", chat)


if __name__ == "__main__":
    unittest.main()
