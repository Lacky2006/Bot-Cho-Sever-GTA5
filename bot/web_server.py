from __future__ import annotations

import re

from aiohttp import web

from .config import Config


SLUG = re.compile(r"^[a-f0-9]{32}$")
FILE = re.compile(r"^[a-zA-Z0-9._-]+$")


class TranscriptWebServer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self.health)
        app.router.add_get("/logs/{slug}/", self.transcript)
        app.router.add_get("/logs/{slug}/assets/{filename}", self.asset)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, self.config.web_host, self.config.web_port).start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    async def health(self, _: web.Request) -> web.Response:
        return web.Response(text="V Roleplay Bot đang hoạt động", content_type="text/plain")

    async def transcript(self, request: web.Request) -> web.StreamResponse:
        slug = request.match_info["slug"]
        if not SLUG.fullmatch(slug):
            raise web.HTTPNotFound()
        path = self.config.transcript_dir / slug / "index.html"
        if not path.is_file():
            raise web.HTTPNotFound(text="Log không tồn tại hoặc đã hết hạn.")
        return web.FileResponse(path, headers={"X-Robots-Tag": "noindex, nofollow"})

    async def asset(self, request: web.Request) -> web.StreamResponse:
        slug, filename = request.match_info["slug"], request.match_info["filename"]
        if not SLUG.fullmatch(slug) or not FILE.fullmatch(filename):
            raise web.HTTPNotFound()
        path = self.config.transcript_dir / slug / "assets" / filename
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"X-Robots-Tag": "noindex, nofollow"})

