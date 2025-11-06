import time
from datetime import UTC, datetime
from typing import Any

import aiofiles
from starlette.types import ASGIApp, Receive, Scope, Send


class TimingMiddleware:
    def __init__(self, application: ASGIApp) -> None:
        self.app: ASGIApp = application

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time: float = time.time()

        async def send_with_timing(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                duration: float = time.time() - start_time
                timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                log_line = (
                    f"Endpoint {scope['raw_path']}. Date {timestamp}. Request duration: {duration:.10f} seconds\n"
                )
                async with aiofiles.open("log_timing.txt", "a", encoding="utf-8") as file:
                    await file.write(log_line)
            await send(message)

        await self.app(scope, receive, send_with_timing)
