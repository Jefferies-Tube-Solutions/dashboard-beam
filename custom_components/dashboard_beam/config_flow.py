"""Configure one paired dashboard or view in the Home Assistant UI."""

import asyncio
import re

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    SelectOptionDict, SelectSelector, SelectSelectorConfig, TextSelector,
    TextSelectorConfig, TextSelectorType,
)

from .client import BeamError, Endpoint, base_url
from .const import DOMAIN
from .local import LocalEndpoint
from .remote import REMOTE_DOMAIN, normalize_prefix, remote_settings, resolve_remote
from .sync import view_path

WHOLE = "__whole__"
NEW = "__new__"
SIDES = ("local", "remote")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def picker(options):
    return SelectSelector(SelectSelectorConfig(options=[
        SelectOptionDict(value=value, label=label) for value, label in options.items()
    ]))


class DashboardBeamFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        options = {}
        for entry in self.hass.config_entries.async_entries(REMOTE_DOMAIN):
            if entry.disabled_by is not None:
                continue
            try:
                url, _, _ = remote_settings(entry)
            except (TypeError, ValueError):
                continue
            options[entry.entry_id] = f"{entry.title} ({url})"
        if not options:
            return await self.async_step_manual()
        if user_input:
            selected = user_input["remote_entry"]
            if selected == NEW:
                return await self.async_step_manual()
            self.data = {"remote_entry_id": selected}
            errors["base"] = await self.load_dashboards()
            if not errors["base"]:
                return await self.async_step_source()
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required("remote_entry", default=next(iter(options))):
                picker({**options, NEW: "Enter remote access manually"}),
        }))

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input:
            try:
                self.data = {
                    "remote_url": base_url(user_input["remote_url"]),
                    "remote_token": user_input["remote_token"].strip(),
                    "prefix": normalize_prefix(user_input.get("prefix")),
                }
            except ValueError:
                errors["base"] = "invalid_input"
            else:
                errors["base"] = await self.load_dashboards()
                if not errors["base"]:
                    return await self.async_step_source()
        return self.async_show_form(step_id="manual", errors=errors, data_schema=vol.Schema({
            vol.Required("remote_url"): str,
            vol.Required("remote_token"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Optional("prefix"): str,
        }))

    async def load_dashboards(self):
        try:
            self.data["remote_url"], _, self.data["prefix"] = resolve_remote(self.hass, self.data)
            self.dashboard_options = []
            self.dashboard_paths = []
            self.dashboard_titles = []
            for side in SIDES:
                async with self.endpoint(side).connect() as connection:
                    if side == "remote":
                        user = await connection.call("auth/current_user")
                        if not user.get("is_admin"):
                            return "remote_not_admin"
                    dashboards = await connection.call("lovelace/dashboards/list")
                self.dashboard_paths.append({item.get("url_path") for item in dashboards})
                titles = {item["url_path"]: item.get("title") or item["url_path"]
                          for item in dashboards if item.get("url_path")}
                self.dashboard_titles.append(titles)
                self.dashboard_options.append({
                    item["url_path"]: f"{titles[item['url_path']]} ({item['url_path']})"
                    for item in dashboards
                    if item.get("mode") == "storage" and item.get("url_path")
                })
        except (BeamError, aiohttp.ClientError, asyncio.TimeoutError):
            return "cannot_connect"
        return None if any(self.dashboard_options) else "no_dashboards"

    def endpoint(self, side):
        if side == "local":
            return LocalEndpoint(self.hass)
        url, token, _ = resolve_remote(self.hass, self.data)
        return Endpoint(async_get_clientsession(self.hass), url, token, "Remote")

    async def async_step_source(self, user_input=None):
        if user_input:
            self.first = int(user_input["initial_source"])
            self.data["initial_source"] = self.first
            return await self.async_step_source_dashboard()
        options = {str(i): f"{side.capitalize()} Home Assistant"
                   for i, side in enumerate(SIDES) if self.dashboard_options[i]}
        return self.async_show_form(step_id="source", data_schema=vol.Schema({
            vol.Required("initial_source"): picker(options),
        }))

    async def view_options(self, side, dashboard):
        async with self.endpoint(side).connect() as connection:
            config = await connection.read(dashboard)
        return {
            path: f"{view.get('title') or f'View {i + 1}'} (/{path})"
            for i, view in enumerate(config["views"])
            if (path := view_path(view, i))
        }

    async def async_step_source_dashboard(self, user_input=None):
        errors = {}
        if user_input:
            side = SIDES[self.first]
            dashboard = user_input["dashboard"]
            try:
                self.source_views = await self.view_options(side, dashboard)
            except (BeamError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                self.data[f"{side}_dashboard"] = dashboard
                return await self.async_step_source_view()
        return self.async_show_form(step_id="source_dashboard", errors=errors, data_schema=vol.Schema({
            vol.Required("dashboard"): picker(self.dashboard_options[self.first]),
        }))

    async def async_step_source_view(self, user_input=None):
        if user_input:
            self.single_view = user_input["view"] != WHOLE
            self.data[f"{SIDES[self.first]}_view"] = user_input["view"] if self.single_view else ""
            return await self.async_step_destination_dashboard()
        return self.async_show_form(step_id="source_view", data_schema=vol.Schema({
            vol.Required("view", default=WHOLE): picker({WHOLE: "Entire dashboard", **self.source_views}),
        }))

    async def async_step_destination_dashboard(self, user_input=None):
        errors = {}
        if user_input:
            side = SIDES[1 - self.first]
            dashboard = user_input["dashboard"]
            self.new_dashboard = dashboard == NEW
            if self.new_dashboard:
                return await self.async_step_new_destination()
            self.data[f"{side}_dashboard"] = dashboard
            if not self.single_view:
                self.data[f"{side}_view"] = ""
                return self.finish()
            try:
                self.destination_views = await self.view_options(side, dashboard)
            except (BeamError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_destination_view()
        return self.async_show_form(step_id="destination_dashboard", errors=errors, data_schema=vol.Schema({
            vol.Required("dashboard"): picker({
                **self.dashboard_options[1 - self.first], NEW: "Create a new dashboard",
            }),
        }))

    async def async_step_destination_view(self, user_input=None):
        if user_input:
            view = user_input["view"]
            if view == NEW:
                return await self.async_step_new_destination()
            self.data[f"{SIDES[1 - self.first]}_view"] = view
            return self.finish()
        return self.async_show_form(step_id="destination_view", data_schema=vol.Schema({
            vol.Required("view"): picker({**self.destination_views, NEW: "Create a new view"}),
        }))

    async def async_step_new_destination(self, user_input=None):
        errors = {}
        target = 1 - self.first
        side = SIDES[target]
        if user_input:
            dashboard = user_input.get("dashboard_path", "").strip()
            title = user_input.get("dashboard_title", "").strip()
            view = user_input.get("view_path", "").strip()
            if self.new_dashboard and (
                not title or not SLUG.fullmatch(dashboard) or "-" not in dashboard
            ):
                errors["base"] = "invalid_dashboard_path"
            elif self.new_dashboard and dashboard in self.dashboard_paths[target]:
                errors["base"] = "destination_exists"
            elif self.single_view and (not SLUG.fullmatch(view) or view.isdecimal()):
                errors["base"] = "invalid_view_path"
            elif self.single_view and not self.new_dashboard and view in self.destination_views:
                errors["base"] = "destination_exists"
            else:
                if self.new_dashboard:
                    self.data[f"{side}_dashboard"] = dashboard
                self.data[f"{side}_view"] = view
                self.data["creation"] = {"dashboard_title": title} if self.new_dashboard else {"view": True}
                if self.new_dashboard and side == "local":
                    return await self.async_step_local_creation()
                return self.finish()
        fields = {}
        if self.new_dashboard:
            fields.update({vol.Required("dashboard_title"): str, vol.Required("dashboard_path"): str})
        if self.single_view:
            fields[vol.Required("view_path")] = str
        return self.async_show_form(step_id="new_destination", errors=errors, data_schema=vol.Schema(fields))

    async def async_step_local_creation(self, user_input=None):
        errors = {}
        if user_input:
            try:
                url = base_url(user_input["local_url"])
                token = user_input["local_token"].strip()
                endpoint = Endpoint(async_get_clientsession(self.hass), url, token, "Local")
                async with endpoint.connect() as connection:
                    user = await connection.call("auth/current_user")
                    local_user = await self.hass.auth.async_get_user(user["id"])
                    if not user.get("is_admin") or local_user is None:
                        raise BeamError("Local administrator credentials required")
            except (ValueError, BeamError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                self.data.update(local_url=url, local_token=token)
                return self.finish()
        try:
            suggested_url = get_url(self.hass)
        except NoURLAvailableError:
            suggested_url = vol.UNDEFINED
        return self.async_show_form(step_id="local_creation", errors=errors, data_schema=vol.Schema({
            vol.Required("local_url", default=suggested_url): str,
            vol.Required("local_token"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }))

    def finish(self):
        for entry in self._async_current_entries():
            for side in SIDES:
                prior = entry.data
                view = self.data[f"{side}_view"]
                other = prior.get(f"{side}_view", "")
                same_instance = side == "local" or (
                    prior["remote_url"].lower() == self.data["remote_url"].lower()
                )
                if (same_instance and prior[f"{side}_dashboard"] == self.data[f"{side}_dashboard"]
                        and (not view or not other or view == other)):
                    return self.async_abort(reason="overlap")
        source, destination = SIDES[self.first], SIDES[1 - self.first]
        title = self.dashboard_titles[self.first][self.data[f"{source}_dashboard"]]
        target_path = self.data[f"{destination}_dashboard"]
        target_title = self.data.get("creation", {}).get("dashboard_title") or (
            self.dashboard_titles[1 - self.first].get(target_path, target_path)
        )
        source_path = self.data[f"{source}_view"]
        target_view = self.data[f"{destination}_view"]
        source_scope = self.source_views[source_path] if self.single_view else "All views"
        target_scope = (
            getattr(self, "destination_views", {}).get(target_view, f"/{target_view}")
            if self.single_view else "All views"
        )
        self.data["service_name"] = f"{source_scope} → {target_title} · {target_scope}"
        return self.async_create_entry(title=title, data=self.data)
