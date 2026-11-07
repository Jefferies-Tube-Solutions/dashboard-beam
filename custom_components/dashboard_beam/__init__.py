"""Run Dashboard Beam automatically and report only blocked rules."""

import asyncio
from contextlib import AsyncExitStack
from datetime import timedelta
import logging

import aiohttp

from homeassistant.components import persistent_notification
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .client import BeamError, Endpoint
from .const import DOMAIN, INTERVAL_SECONDS
from .local import LocalEndpoint
from .remote import resolve_remote
from .sync import reconcile

LOGGER = logging.getLogger(__name__)


class Rule:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.error = None
        self.checked = False
        self.task = None
        self.watch_task = None
        self.stopping = False
        self.pending = False
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.store = Store(hass, 1, self.signal)
        self.state = {}

    @callback
    def trigger(self, _=None):
        if self.stopping:
            return
        self.pending = True
        if self.task is None or self.task.done():
            self.task = self.entry.async_create_background_task(self.hass, self.run(), self.signal)

    def endpoint(self, side):
        data = self.entry.data
        session = async_get_clientsession(self.hass)
        if side == "local":
            dashboard_api = (
                Endpoint(session, data["local_url"], data["local_token"], "Local")
                if data.get("local_url") and data.get("local_token") else None
            )
            return LocalEndpoint(self.hass, dashboard_api)
        url, token, _ = resolve_remote(self.hass, data)
        return Endpoint(session, url, token, "Remote")

    @callback
    def local_dashboard_updated(self, event):
        if event.data.get("url_path") == self.entry.data["local_dashboard"]:
            self.trigger()

    async def watch_remote(self):
        while True:
            try:
                async with self.endpoint("remote").connect() as connection:
                    await connection.watch_dashboard(self.entry.data["remote_dashboard"], self.trigger)
            except (BeamError, TimeoutError, aiohttp.ClientError, ValueError, TypeError):
                # Polling keeps working if the remote event stream is unavailable.
                pass
            await asyncio.sleep(30)

    async def run(self):
        data = self.entry.data
        # Two separate view rules may share a destination dashboard.
        lock = self.hass.data.setdefault(DOMAIN, asyncio.Lock())
        while self.pending:
            self.pending = False
            error = None
            try:
                async with lock, asyncio.timeout(120), AsyncExitStack() as stack:
                    connections = []
                    for side in ("local", "remote"):
                        connections.append(await stack.enter_async_context(self.endpoint(side).connect()))
                    await reconcile(
                        connections, {**data, "prefix": resolve_remote(self.hass, data)[2]},
                        self.state, self.store,
                    )
            except BeamError as exc:
                error = str(exc)
            except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
                error = f"Home Assistant connection or response failed ({type(exc).__name__})."
            except Exception:
                LOGGER.exception("Unexpected Dashboard Beam failure")
                error = "Unexpected replication error. Check the Home Assistant log."
            if not self.checked or error != self.error:
                self.checked = True
                self.error = error
                if error:
                    persistent_notification.async_create(
                        self.hass, f"{self.entry.title}\n\n{error}",
                        title="Dashboard Beam · Replication blocked", notification_id=self.signal,
                    )
                else:
                    persistent_notification.async_dismiss(self.hass, self.signal)
                async_dispatcher_send(self.hass, self.signal)


async def async_setup_entry(hass, entry):
    rule = entry.runtime_data = Rule(hass, entry)
    rule.state = await rule.store.async_load() or {}
    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])
    entry.async_on_unload(async_track_time_interval(
        hass, rule.trigger, timedelta(seconds=INTERVAL_SECONDS)
    ))
    entry.async_on_unload(hass.bus.async_listen("lovelace_updated", rule.local_dashboard_updated))
    rule.watch_task = entry.async_create_background_task(
        hass, rule.watch_remote(), f"{rule.signal}_remote_events"
    )
    rule.trigger()
    return True


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"])
    if unloaded:
        rule = entry.runtime_data
        rule.stopping = True
        tasks = [task for task in (rule.task, rule.watch_task) if task and not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        persistent_notification.async_dismiss(hass, rule.signal)
    return unloaded


async def async_remove_entry(hass, entry):
    await Store(hass, 1, f"{DOMAIN}_{entry.entry_id}").async_remove()
