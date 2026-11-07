"""Compare and reconcile one Lovelace dashboard or view pair."""

from copy import deepcopy
from hashlib import sha256
import json
import re
import unicodedata

from .client import BeamError, DashboardNotFound, IMAGE, MEDIA

ENTITY = re.compile(r"\b[a-z_][a-z0-9_]*\.[a-z0-9_]+\b")
ENTITY_FIELDS = {"entity", "entity_id", "entities"}
IMAGE_FIELDS = {"image", "background", "state_image", "dark_image"}
LOCAL_IMAGE = re.compile(r"/local/[^\s'\")]+")
EMBEDDED_IMAGE = re.compile(r"(?P<quote>['\"]?)(?P<url>/(?:local|api/image/serve)/[^\s'\")]+)(?P=quote)")
ASSET = re.compile(r"beam-image://([a-f0-9]{64})")
MAPPED_ENTITY = re.compile(r"beam-entity://([a-z_][a-z0-9_]*\.[a-z0-9_]+)")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def view_path(view, index):
    """Use the URL Home Assistant exposes, including positional routes."""
    return view.get("path") or str(index)


def destination_path(name, occupied, *, dashboard=False):
    """Generate a valid, unused route without requiring a URL from the user."""
    transliterated = name.lower().translate(str.maketrans({"æ": "ae", "ø": "oe", "å": "aa"}))
    ascii_name = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    if not base:
        base = "beam-dashboard" if dashboard else "beam-view"
    elif dashboard and "-" not in base:
        base = f"{base}-dashboard"
    elif not dashboard and base.isdecimal():
        base = f"view-{base}"
    candidate = base
    suffix = 2
    while candidate in occupied:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def view_index(config, path):
    matches = [index for index, view in enumerate(config["views"])
               if view_path(view, index) == path]
    if len(matches) > 1:
        raise BeamError(f"Ambiguous view path {path!r}")
    return matches[0] if matches else None


def select(config, path):
    if not path:
        return config
    index = view_index(config, path)
    if index is None:
        raise BeamError(f"Expected exactly one view with path {path!r}")
    return {key: value for key, value in config["views"][index].items() if key != "path"}


def replace(config, path, value, *, append=False):
    if not path:
        return value
    result = deepcopy(config)
    index = view_index(result, path)
    if append and index is None:
        result["views"].append({**value, "path": path})
    elif index is not None and not append:
        existing = result["views"][index]
        result["views"][index] = {**value, **({"path": existing["path"]} if "path" in existing else {})}
    else:
        raise BeamError(f"Destination view {path!r} changed during sync")
    return result


def choose(current, previous, first):
    """Return the side to send, or None when the normalized content matches."""
    if current[0] == current[1]:
        return None
    if previous is None:
        return first
    changed = [i for i in range(2) if current[i] != previous[i]]
    if len(changed) == 1:
        return changed[0]
    raise BeamError("Both sides differ since the last successful sync. Make the views match to resume.")


class Normalizer:
    """Translate known entity references and canonicalize local image bytes."""

    def __init__(self, endpoints, states, prefix, images):
        self.endpoints = endpoints
        self.states = states
        self.prefix = prefix
        self.images = images
        self.paths = [{}, {}]
        self.missing = set()
        self.payloads = {}

    def entity(self, entity_id, side, location):
        domain, name = entity_id.split(".", 1)
        canonical = name.removeprefix(self.prefix) if side == 0 else name
        expected = (f"{domain}.{self.prefix}{canonical}", f"{domain}.{canonical}")
        if entity_id != expected[side]:
            self.missing.add(f"{self.endpoints[side].label}: unmapped {entity_id} at {location}")
        for index, target in enumerate(expected):
            if target not in self.states[index]:
                self.missing.add(f"{self.endpoints[index].label}: missing {target} at {location}")
        return "beam-entity://" + expected[1]

    async def asset(self, value, side):
        match = IMAGE.fullmatch(value) or MEDIA.fullmatch(value)
        if match:
            value = f"/api/image/serve/{match[1]}/original"
        if not match and not LOCAL_IMAGE.fullmatch(value):
            if value.startswith(("/api/", "media-source:", "//")):
                raise BeamError(f"Unsupported local image reference on {self.endpoints[side].label}: {value}")
            return value
        if value not in self.paths[side]:
            data, kind = await self.endpoints[side].download(value)
            hash_ = sha256(data).hexdigest()
            self.paths[side][value] = hash_
            self.images[side][hash_] = value
            self.payloads[hash_] = (data, kind)
        return "beam-image://" + self.paths[side][value]

    async def normalize(self, value, side, location="$", field=""):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                child_field = field if field == "state_image" else key
                result[key] = await self.normalize(item, side, f"{location}.{key}", child_field)
            return result
        if isinstance(value, list):
            return [await self.normalize(item, side, f"{location}[{i}]", field)
                    for i, item in enumerate(value)]
        if not isinstance(value, str):
            return value
        if field in IMAGE_FIELDS:
            if value.startswith("url("):
                return await self.css_image(value, side)
            return await self.asset(value, side)
        if field in ENTITY_FIELDS:
            return ENTITY.sub(lambda match: self.entity(match[0], side, location), value)
        if "{{" in value or "{%" in value or "[[[" in value:
            return ENTITY.sub(lambda match: self.entity(match[0], side, location)
                              if match[0] in self.states[side] else match[0], value)
        return value

    async def css_image(self, value, side):
        for match in tuple(EMBEDDED_IMAGE.finditer(value)):
            value = value.replace(match["url"], await self.asset(match["url"], side))
        return value

    async def materialize(self, value, side):
        if isinstance(value, dict):
            return {key: await self.materialize(item, side) for key, item in value.items()}
        if isinstance(value, list):
            return [await self.materialize(item, side) for item in value]
        if not isinstance(value, str):
            return value
        for hash_ in set(ASSET.findall(value)):
            if hash_ not in self.images[side]:
                self.images[side][hash_] = await self.endpoints[side].upload(*self.payloads[hash_])
            value = value.replace("beam-image://" + hash_, self.images[side][hash_])
        return MAPPED_ENTITY.sub(
            lambda match: self.prefixed(match[1]) if side == 0 else match[1], value
        )

    def prefixed(self, entity_id):
        domain, name = entity_id.split(".", 1)
        target = f"{domain}.{self.prefix}{name}"
        return target if entity_id in self.states[1] and target in self.states[0] else entity_id


async def reconcile(connections, config, state, store):
    paths = (config["local_dashboard"], config["remote_dashboard"])
    views = (config.get("local_view"), config.get("remote_view"))
    first = config["initial_source"]
    target = 1 - first
    creation = config.get("creation") if state.get("baseline") is None else None
    named_view = config.get("creation", {}).get("view_title")
    new_dashboard = creation and creation.get("dashboard_title")
    target_conn = connections[target]
    if new_dashboard:
        existing = await dashboard_record(target_conn, paths[target])
        if existing and existing.get("id") != state.get("created_dashboard"):
            raise BeamError(f"Destination dashboard {paths[target]!r} already exists")

    async def read_side(i):
        try:
            return await connections[i].read(paths[i])
        except DashboardNotFound:
            if new_dashboard and i == target:
                return None
            raise

    configs = [await read_side(i) for i in range(2)]
    selected = []
    for i, (item, view) in enumerate(zip(configs, views)):
        if i == target and creation and (item is None or (view and view_index(item, view) is None)):
            selected.append(None)
        else:
            selected.append(select(item, view))
    states = [{item["entity_id"] for item in await conn.call("get_states")} for conn in connections]
    images = state.setdefault("images", [{}, {}])
    normalizer = Normalizer([conn.endpoint for conn in connections], states, config["prefix"], images)
    normalized = [await normalizer.normalize(item, i) for i, item in enumerate(selected)]
    if named_view:
        for item in normalized:
            if item is not None:
                item.pop("title", None)
    current = [digest(item) for item in normalized]
    if creation and selected[target] is not None:
        pending = state.get("pending_creation")
        if current[target] != pending:
            raise BeamError("The requested destination already contains a configuration")
        # A previous save succeeded before the baseline could be persisted.
        state["baseline"] = [pending, pending]
        await store.async_save(state)
        return
    source = first if creation else choose(current, state.get("baseline"), first)
    if source is None:
        missing = normalizer.missing
    else:
        normalizer.missing.clear()
        await normalizer.normalize(selected[source], source)
        missing = normalizer.missing
    if missing:
        raise BeamError("\n".join(sorted(missing)))
    if source is not None:
        destination = 1 - source
        # Ignore remembered image IDs until their bytes have been verified this run.
        for hash_, path in tuple(images[destination].items()):
            if path not in normalizer.paths[destination]:
                try:
                    data, _ = await connections[destination].endpoint.download(path)
                except BeamError:
                    del images[destination][hash_]
                else:
                    if sha256(data).hexdigest() != hash_:
                        del images[destination][hash_]
        value = await normalizer.materialize(normalized[source], destination)
        if named_view:
            existing_view = selected[destination]
            if existing_view is not None and "title" in existing_view:
                value["title"] = existing_view["title"]
            elif existing_view is None:
                value["title"] = named_view
        await store.async_save(state)
        for i in range(2):
            if await read_side(i) != configs[i]:
                raise BeamError("Dashboard changed during sync. Beam will retry.")
        if new_dashboard:
            record = await dashboard_record(target_conn, paths[target])
            if record is None:
                record = await target_conn.call(
                    "lovelace/dashboards/create", url_path=paths[target], mode="storage",
                    title=new_dashboard, require_admin=True, show_in_sidebar=True,
                )
                state["created_dashboard"] = record["id"]
                await store.async_save(state)
            elif record["id"] != state.get("created_dashboard"):
                raise BeamError(f"Destination dashboard {paths[target]!r} already exists")
            if await read_side(target) != configs[target]:
                raise BeamError("Destination dashboard changed during creation. Beam will retry.")
        new = replace(configs[destination] or {"views": []}, views[destination], value,
                      append=bool(creation and views[destination]))
        if creation:
            state["pending_creation"] = current[source]
            await store.async_save(state)
        await connections[destination].call("lovelace/config/save", url_path=paths[destination], config=new)
        current[destination] = current[source]
    if state.get("baseline") != current:
        state["baseline"] = current
        await store.async_save(state)


async def dashboard_record(connection, path):
    dashboards = await connection.call("lovelace/dashboards/list")
    return next((item for item in dashboards if item.get("url_path") == path), None)
