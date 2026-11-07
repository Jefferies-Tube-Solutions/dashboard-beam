"""Read a selected Remote Home-Assistant connection without copying its token."""

import re
from urllib.parse import urlsplit

from .client import BeamError, base_url

REMOTE_DOMAIN = "remote_homeassistant"


def normalize_prefix(value):
    prefix = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]*", prefix):
        raise ValueError("Invalid entity prefix")
    return prefix


def remote_settings(entry):
    host = entry.data.get("host")
    token = entry.data.get("access_token")
    if not isinstance(host, str) or not host or not isinstance(token, str) or not token:
        raise ValueError("Not an outbound Remote Home-Assistant connection")
    port = int(entry.data.get("port", 8123))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid remote port")
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    scheme = "https" if entry.data.get("secure") else "http"
    origin = base_url(f"{scheme}://{host}:{port}")
    if urlsplit(origin).port != port:
        raise ValueError("Invalid remote host")
    prefix = normalize_prefix(entry.options.get("entity_prefix", entry.data.get("entity_prefix")))
    return origin, token, prefix


def resolve_remote(hass, data):
    if entry_id := data.get("remote_entry_id"):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != REMOTE_DOMAIN or entry.disabled_by is not None:
            raise BeamError("The selected Remote Home-Assistant connection is unavailable.")
        try:
            return remote_settings(entry)
        except (TypeError, ValueError) as exc:
            raise BeamError("The selected Remote Home-Assistant connection is invalid.") from exc
    return data["remote_url"], data["remote_token"], normalize_prefix(data["prefix"])
