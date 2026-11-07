"""Configure one paired dashboard or view in the Home Assistant UI."""

import asyncio
import re

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict, SelectSelector, SelectSelectorConfig, TextSelector,
    TextSelectorConfig, TextSelectorType,
)

from .client import BeamError, Endpoint, base_url
from .const import DOMAIN
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
        if user_input:
            try:
                self.data = {
                    **user_input,
                    "local_url": base_url(user_input["local_url"]),
                    "remote_url": base_url(user_input["remote_url"]),
                    "prefix": user_input["prefix"].strip(),
                }
                if self.data["local_url"].lower() == self.data["remote_url"].lower():
                    raise ValueError("Use two distinct Home Assistant origins")
                if not re.fullmatch(r"[a-z0-9_]*", self.data["prefix"]):
                    raise ValueError("Invalid prefix")
                self.dashboard_options = []
                self.dashboard_paths = []
                self.dashboard_titles = []
                for side in SIDES:
                    async with self.endpoint(side).connect() as connection:
                        user = await connection.call("auth/current_user")
                        if not user.get("is_admin"):
                            raise BeamError("Administrator credentials required")
                        dashboards = await connection.call("lovelace/dashboards/list")
                        self.dashboard_paths.append({item.get("url_path") for item in dashboards})
                        self.dashboard_titles.append({
                            item["url_path"]: item["title"] for item in dashboards if item.get("url_path")
                        })
                        self.dashboard_options.append({
                            item["url_path"]: f"{item['title']} ({item['url_path']})"
                            for item in dashboards
                            if item.get("mode") == "storage" and item.get("url_path")
                        })
                if not any(self.dashboard_options):
                    errors["base"] = "no_dashboards"
                else:
                    return await self.async_step_source()
            except ValueError:
                errors["base"] = "invalid_input"
            except (BeamError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
        password = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
        prefixes = {
            entry.options.get("entity_prefix", entry.data.get("entity_prefix", ""))
            for entry in self.hass.config_entries.async_entries("remote_homeassistant")
        } - {"", None}
        prefix = next(iter(prefixes)) if len(prefixes) == 1 else ""
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required("local_url"): str, vol.Required("local_token"): password,
            vol.Required("remote_url"): str, vol.Required("remote_token"): password,
            vol.Required("prefix", default=prefix): str,
        }))

    def endpoint(self, side):
        return Endpoint(async_get_clientsession(self.hass), self.data[f"{side}_url"],
                        self.data[f"{side}_token"], side.capitalize())

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
                return self.finish()
        fields = {}
        if self.new_dashboard:
            fields.update({vol.Required("dashboard_title"): str, vol.Required("dashboard_path"): str})
        if self.single_view:
            fields[vol.Required("view_path")] = str
        return self.async_show_form(step_id="new_destination", errors=errors, data_schema=vol.Schema(fields))

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
