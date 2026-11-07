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

WHOLE = "__whole__"


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
                for side in ("local", "remote"):
                    async with self.endpoint(side).connect() as connection:
                        user = await connection.call("auth/current_user")
                        if not user.get("is_admin"):
                            raise BeamError("Administrator credentials required")
                        dashboards = await connection.call("lovelace/dashboards/list")
                        self.dashboard_options.append({
                            item["url_path"]: f"{item['title']} ({item['url_path']})"
                            for item in dashboards
                            if item.get("mode") == "storage" and item.get("url_path")
                        })
                if not all(self.dashboard_options):
                    errors["base"] = "no_dashboards"
                else:
                    return await self.async_step_dashboards()
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

    async def async_step_dashboards(self, user_input=None):
        errors = {}
        if user_input:
            self.data.update(user_input)
            try:
                self.view_options = []
                for side in ("local", "remote"):
                    async with self.endpoint(side).connect() as connection:
                        config = await connection.read(self.data[f"{side}_dashboard"])
                    self.view_options.append({WHOLE: "Entire dashboard", **{
                        view["path"]: f"{view.get('title') or view['path']} ({view['path']})"
                        for view in config["views"] if view.get("path")
                    }})
                return await self.async_step_views()
            except (BeamError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="dashboards", errors=errors, data_schema=vol.Schema({
            vol.Required("local_dashboard"): picker(self.dashboard_options[0]),
            vol.Required("remote_dashboard"): picker(self.dashboard_options[1]),
        }))

    async def async_step_views(self, user_input=None):
        errors = {}
        if user_input:
            local, remote = user_input["local_view"], user_input["remote_view"]
            if (local == WHOLE) != (remote == WHOLE):
                errors["base"] = "mismatched_scope"
            else:
                self.data.update({
                    "local_view": "" if local == WHOLE else local,
                    "remote_view": "" if remote == WHOLE else remote,
                    "initial_source": int(user_input["initial_source"]),
                })
                for entry in self._async_current_entries():
                    for side in ("local", "remote"):
                        prior = entry.data
                        view = self.data[f"{side}_view"]
                        other = prior.get(f"{side}_view", "")
                        same_instance = side == "local" or (
                            prior["remote_url"].lower() == self.data["remote_url"].lower()
                        )
                        if (same_instance and prior[f"{side}_dashboard"] == self.data[f"{side}_dashboard"]
                                and (not view or not other or view == other)):
                            return self.async_abort(reason="overlap")
                title = f"{self.data['local_dashboard']} ↔ {self.data['remote_dashboard']}"
                if local != WHOLE:
                    title = f"{title} · {local} ↔ {remote}"
                return self.async_create_entry(title=title, data=self.data)
        return self.async_show_form(step_id="views", errors=errors, data_schema=vol.Schema({
            vol.Required("local_view", default=WHOLE): picker(self.view_options[0]),
            vol.Required("remote_view", default=WHOLE): picker(self.view_options[1]),
            vol.Required("initial_source"): picker({"0": "Local Home Assistant", "1": "Remote Home Assistant"}),
        }))
