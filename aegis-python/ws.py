from __future__ import annotations

import random
import time
from typing import Callable

from websocket import WebSocketApp


class AegisWebSocketClient:
    def __init__(
        self,
        base_url: str,
        get_jwt: Callable[[], str | None],
        channels: list[str] | None = None,
        max_backoff_seconds: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._get_jwt = get_jwt
        self._channels = channels or ["alerts"]
        self._max_backoff = max_backoff_seconds

    def run_forever(self, on_message: Callable[[str], None]) -> None:
        backoff = 0.5
        while True:
            token = self._get_jwt()
            if not token:
                raise RuntimeError("JWT token is required for websocket connection")

            url = f"{self._base_url}?token={token}&channels={','.join(self._channels)}"
            app = WebSocketApp(
                url,
                on_message=lambda _socket, message: on_message(message),
            )
            app.run_forever()
            sleep_for = min(backoff + random.random() * 0.25, self._max_backoff)
            time.sleep(sleep_for)
            backoff = min(backoff * 2, self._max_backoff)
