import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from api_client import AireApiClient


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
