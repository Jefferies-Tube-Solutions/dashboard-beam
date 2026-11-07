"""Use the running Home Assistant instance for local dashboard operations."""

from contextlib import asynccontextmanager
from copy import deepcopy
from io import BytesIO
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import unquote

from aiohttp.web_request import FileField
from multidict import CIMultiDict, CIMultiDictProxy

from homeassistant.components.lovelace.const import ConfigNotFound, LOVELACE_DATA

from .client import BeamError, DashboardNotFound, IMAGE, IMAGE_TYPES, MAX_BYTES


class LocalEndpoint:
    label = "Local"

    def __init__(self, hass, dashboard_api=None):
        self.hass = hass
        self.endpoint = self
        self.dashboard_api = dashboard_api

    @asynccontextmanager
    async def connect(self):
        yield self

    @property
    def dashboards(self):
        return self.hass.data[LOVELACE_DATA].dashboards

    def dashboard(self, path):
        if (dashboard := self.dashboards.get(path)) is None:
            raise DashboardNotFound(f"Local: dashboard {path!r} was not found")
        return dashboard

    async def read(self, path):
        try:
            value = await self.dashboard(path).async_load(False)
        except ConfigNotFound as exc:
            raise DashboardNotFound(f"Local: dashboard {path!r} has no saved configuration") from exc
        if not isinstance(value, dict) or not isinstance(value.get("views"), list):
            raise BeamError("Local: expected an editable dashboard with views")
        return deepcopy(value)

    async def call(self, command, **params):
        if command == "get_states":
            return [{"entity_id": entity_id} for entity_id in self.hass.states.async_entity_ids()]
        if command == "lovelace/dashboards/list":
            return [{**(item.config or {}), "url_path": path, "mode": item.mode}
                    for path, item in self.dashboards.items() if path is not None]
        if command == "lovelace/config/save":
            dashboard = self.dashboard(params["url_path"])
            if dashboard.mode != "storage":
                raise BeamError("Local: the destination dashboard must use storage mode")
            await dashboard.async_save(params["config"])
            return None
        if command == "lovelace/dashboards/create" and self.dashboard_api:
            async with self.dashboard_api.connect() as connection:
                return await connection.call(command, **params)
        raise BeamError(f"Local: unsupported operation {command}")

    async def download(self, path):
        if match := IMAGE.fullmatch(path):
            image = self.hass.data["image_upload"].data.get(match[1])
            if not image:
                raise BeamError(f"Local: cannot read image {path}")
            root = self.hass.config.path("image")
            relative = f"{match[1]}/original"
            kind = image["content_type"]
        else:
            root = self.hass.config.path("www")
            relative = unquote(path.removeprefix("/local/"))
            kind = guess_type(relative)[0]
        if kind not in IMAGE_TYPES:
            raise BeamError(f"Local: unsupported image {path}")
        try:
            return await self.hass.async_add_executor_job(read_image, root, relative), kind
        except OSError as exc:
            raise BeamError(f"Local: cannot read image {path}") from exc

    async def upload(self, data, kind):
        with BytesIO(data) as stream:
            file = FileField("file", f"dashboard-beam.{IMAGE_TYPES[kind]}", stream, kind,
                             CIMultiDictProxy(CIMultiDict()))
            record = await self.hass.data["image_upload"].async_create_item({"file": file})
        return f"/api/image/serve/{record['id']}/original"


def read_image(root, relative):
    directory = Path(root).resolve()
    file = (directory / relative).resolve()
    if not file.is_relative_to(directory):
        raise OSError("Image path leaves its configured directory")
    with file.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise OSError("Image exceeds 9 MiB")
    return data
