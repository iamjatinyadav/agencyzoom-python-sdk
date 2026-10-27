"""Connection-pool checks against a real loopback HTTP server, without credentials."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agencyzoom import AgencyZoomError, AsyncAgencyZoom


@pytest.fixture
def server() -> Iterator[tuple[str, list[int]]]:
    peers: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            peers.append(self.client_address[1])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, format: str, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    worker = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", peers
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


def test_real_pool_reuses_connections_and_rejects_another_loop(
    server: tuple[str, list[int]],
) -> None:
    url, peers = server
    client = AsyncAgencyZoom(
        token="synthetic-token", base_url=url, rate_limit_per_minute=None, max_retries=0
    )
    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(client.settings.employees()) == []
        assert loop.run_until_complete(client.settings.employees()) == []
        assert len(peers) == 2
        assert peers[0] == peers[1]
        with pytest.raises(AgencyZoomError, match="one event loop"):
            asyncio.run(client.settings.employees())
        assert len(peers) == 2
    finally:
        loop.run_until_complete(client.close())
        loop.close()


async def test_clones_share_loop_affinity_and_cache_cannot_bypass_it(
    server: tuple[str, list[int]],
) -> None:
    url, peers = server
    async with AsyncAgencyZoom(
        token="synthetic-token", base_url=url, cache_ttl=300, rate_limit_per_minute=None
    ) as client:
        assert await client.settings.employees() == []
        clone = client.with_options(timeout=5)
        assert await clone.settings.employees() == []
        assert len(peers) == 1

        def other_loop() -> None:
            with pytest.raises(AgencyZoomError, match="one event loop"):
                asyncio.run(clone.settings.employees())

        await asyncio.get_running_loop().run_in_executor(None, other_loop)
        assert len(peers) == 1
