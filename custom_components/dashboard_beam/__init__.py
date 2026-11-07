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
from .sync import reconcile

LOGGER = logging.getLogger(__name__)


class Rule:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.error = None
        self.checked = False
        self.task = None
        self.pending = False
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.store = Store(hass, 1, self.signal)
        self.state = {}

    @callback
    def trigger(self, _=None):
        self.pending = True
        if self.task is None or self.task.done():
            self.task = self.entry.async_create_background_task(self.hass, self.run(), self.signal)

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
                        endpoint = Endpoint(async_get_clientsession(self.hass),
                                            data[f"{side}_url"], data[f"{side}_token"],
                                            side.capitalize())
                        connections.append(await stack.enter_async_context(endpoint.connect()))
                    await reconcile(connections, data, self.state, self.store)
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
    rule.trigger()
    return True


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"])
    if unloaded:
        rule = entry.runtime_data
        if rule.task and not rule.task.done():
            rule.task.cancel()
            await asyncio.gather(rule.task, return_exceptions=True)
        persistent_notification.async_dismiss(hass, rule.signal)
    return unloaded


async def async_remove_entry(hass, entry):
    await Store(hass, 1, f"{DOMAIN}_{entry.entry_id}").async_remove()
