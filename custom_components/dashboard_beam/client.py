"""Authenticated Home Assistant dashboard and image access."""

from contextlib import asynccontextmanager
import re
from urllib.parse import urlsplit


class BeamError(Exception):
    """A rule cannot be completed."""


IMAGE = re.compile(r"/api/image/serve/([a-f0-9]{32})/(?:original|[^/?#]+)")
MEDIA = re.compile(r"media-source://image_upload/([a-f0-9]{32})")
IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}
MAX_BYTES = 9 * 1024 * 1024


def base_url(value):
    """Accept an HA origin without credentials, fragments or query parameters."""
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("Expected an http(s) Home Assistant origin")
    return value


class Endpoint:
    def __init__(self, session, url, token, label):
        self.session = session
        self.url = url
        self.token = token
        self.label = label

    @asynccontextmanager
    async def connect(self):
        import aiohttp

        async with self.session.ws_connect(
            self.url.replace("http", "ws", 1) + "/api/websocket",
            max_msg_size=16 * 1024 * 1024,
            timeout=aiohttp.ClientWSTimeout(ws_receive=20),
        ) as ws:
            if (await ws.receive_json()).get("type") != "auth_required":
                raise BeamError(f"{self.label}: unexpected WebSocket handshake")
            await ws.send_json({"type": "auth", "access_token": self.token})
            if (await ws.receive_json()).get("type") != "auth_ok":
                raise BeamError(f"{self.label}: authentication failed")
            yield Connection(self, ws)

    async def download(self, path):
        import aiohttp

        async with self.session.get(
            self.url + path, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=20)
        ) as response:
            kind = response.content_type
            if response.status != 200 or kind not in IMAGE_TYPES:
                raise BeamError(f"{self.label}: cannot read image {path}")
            data = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise BeamError(f"{self.label}: image exceeds 9 MiB: {path}")
            return bytes(data), kind

    async def upload(self, data, kind):
        import aiohttp

        form = aiohttp.FormData()
        form.add_field("file", data, filename=f"dashboard-beam.{IMAGE_TYPES[kind]}", content_type=kind)
        async with self.session.post(
            self.url + "/api/image/upload", data=form, allow_redirects=False,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=aiohttp.ClientTimeout(total=25),
        ) as response:
            if response.status != 200:
                raise BeamError(f"{self.label}: image upload failed (HTTP {response.status})")
            image_id = (await response.json()).get("id", "")
            if not re.fullmatch(r"[a-f0-9]{32}", image_id):
                raise BeamError(f"{self.label}: invalid uploaded image ID")
            return f"/api/image/serve/{image_id}/original"


class Connection:
    def __init__(self, endpoint, ws):
        self.endpoint = endpoint
        self.ws = ws
        self.command_id = 0

    async def call(self, command, **params):
        self.command_id += 1
        await self.ws.send_json({"id": self.command_id, "type": command, **params})
        result = await self.ws.receive_json()
        if result.get("id") != self.command_id or not result.get("success"):
            code = result.get("error", {}).get("code", "unexpected_result")
            raise BeamError(f"{self.endpoint.label}: {command} failed ({code})")
        return result.get("result")

    async def read(self, path):
        config = await self.call("lovelace/config", url_path=path)
        if not isinstance(config, dict) or not isinstance(config.get("views"), list):
            raise BeamError(f"{self.endpoint.label}: expected an editable dashboard with views")
        return config
