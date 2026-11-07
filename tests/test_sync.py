"""Synthetic end-to-end reconciliation tests without a Home Assistant runtime."""

from copy import deepcopy
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

PACKAGE = "beam_under_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "dashboard_beam")]
sys.modules[PACKAGE] = package
sync = importlib.import_module(f"{PACKAGE}.sync")
client = importlib.import_module(f"{PACKAGE}.client")


class FakeHome:
    def __init__(self, label, path, entity):
        self.endpoint = self
        self.label = label
        self.entity = entity
        self.config = {"views": [
            {"path": path, "title": "Old", "cards": [{"entity": entity}]},
            {"path": "other", "title": "Keep me"},
        ]}
        self.writes = 0
        self.uploads = 0
        self.images = {}
        self.dashboard = None
        self.creates = 0

    async def read(self, path):
        if self.config is None:
            raise client.DashboardNotFound(path)
        return deepcopy(self.config)

    async def call(self, command, **params):
        if command == "get_states":
            return [{"entity_id": self.entity}]
        if command == "lovelace/dashboards/list":
            return [self.dashboard] if self.dashboard else []
        if command == "lovelace/dashboards/create":
            self.creates += 1
            self.dashboard = {"id": "new-id", **params}
            return self.dashboard
        self.config = params["config"]
        self.writes += 1

    async def download(self, path):
        return self.images[path], "image/png"

    async def upload(self, data, kind):
        self.uploads += 1
        path = f"/api/image/serve/{self.uploads:032x}/original"
        self.images[path] = data
        return path


class FakeStore:
    async def async_save(self, state):
        self.saved = deepcopy(state)


def synchronous_test(test):
    """Drive the in-memory coroutine, which never waits on external I/O."""
    def run(self):
        with self.assertRaises(StopIteration):
            test(self).send(None)
    return run


class ReplicationTest(unittest.TestCase):
    def setUp(self):
        self.local = FakeHome("Local", "home-4", "light.cabin_porch")
        self.remote = FakeHome("Remote", "porch", "light.porch")
        self.rule = dict(local_dashboard="cabin", remote_dashboard="house", local_view="home-4",
                         remote_view="porch", prefix="cabin_", initial_source=0)
        self.state = {}
        self.store = FakeStore()

    async def run_rule(self):
        await sync.reconcile([self.local, self.remote], self.rule, self.state, self.store)

    @synchronous_test
    async def test_view_round_trip_and_sibling(self):
        await self.run_rule()
        self.local.config["views"][0]["title"] = "Local change"
        await self.run_rule()
        self.assertEqual(self.remote.config["views"][0]["cards"][0]["entity"], "light.porch")
        self.assertEqual(self.remote.config["views"][0]["title"], "Local change")
        self.assertEqual(self.remote.config["views"][1], {"path": "other", "title": "Keep me"})
        self.remote.config["views"][0]["title"] = "Remote change"
        await self.run_rule()
        self.assertEqual(self.local.config["views"][0]["cards"][0]["entity"], "light.cabin_porch")
        self.assertEqual(self.local.config["views"][0]["title"], "Remote change")
        await self.run_rule()
        self.assertEqual((self.local.writes, self.remote.writes), (1, 1))

    @synchronous_test
    async def test_missing_entity_blocks_write(self):
        self.local.config["views"][0]["cards"][0]["entity"] = "light.cabin_missing"
        with self.assertRaisesRegex(sync.BeamError, "Remote: missing light.missing"):
            await self.run_rule()
        self.assertEqual(self.remote.writes, 0)

    @synchronous_test
    async def test_concurrent_edits_block(self):
        await self.run_rule()
        self.local.config["views"][0]["title"] = "Local change"
        self.remote.config["views"][0]["title"] = "Remote change"
        with self.assertRaisesRegex(sync.BeamError, "Both sides differ"):
            await self.run_rule()
        self.assertEqual((self.local.writes, self.remote.writes), (0, 0))

    @synchronous_test
    async def test_local_picture_is_uploaded_and_stable(self):
        self.local.images["/local/floor.png"] = b"synthetic image"
        self.local.config["views"][0]["cards"][0]["image"] = "/local/floor.png"
        await self.run_rule()
        self.assertEqual(self.remote.uploads, 1)
        await self.run_rule()
        self.assertEqual((self.remote.uploads, self.remote.writes), (1, 1))

    @synchronous_test
    async def test_positional_view_round_trip_preserves_absent_path(self):
        del self.remote.config["views"][0]["path"]
        self.rule["remote_view"] = "0"
        await self.run_rule()
        self.local.config["views"][0]["title"] = "Local change"
        await self.run_rule()
        self.assertNotIn("path", self.remote.config["views"][0])
        self.assertEqual(self.remote.config["views"][0]["title"], "Local change")
        self.remote.config["views"][0]["title"] = "Remote change"
        await self.run_rule()
        self.assertEqual(self.local.config["views"][0]["title"], "Remote change")

    @synchronous_test
    async def test_append_new_view_from_remote_and_preserve_existing_views(self):
        original = deepcopy(self.local.config["views"])
        self.rule.update(local_view="new-view", initial_source=1, creation={"view": True})
        await self.run_rule()
        await self.run_rule()
        self.assertEqual(self.local.config["views"][:2], original)
        self.assertEqual(self.local.config["views"][2]["path"], "new-view")
        self.assertEqual(self.local.config["views"][2]["cards"][0]["entity"], self.local.entity)
        self.assertEqual(self.local.writes, 1)

    @synchronous_test
    async def test_new_dashboard_can_receive_a_whole_dashboard_or_one_view(self):
        for whole in (True, False):
            with self.subTest(whole=whole):
                self.setUp()
                self.remote.config = None
                self.rule.update(creation={"dashboard_title": "Beam Copy"})
                if whole:
                    self.rule.update(local_view="", remote_view="")
                await self.run_rule()
                await self.run_rule()
                self.assertEqual(self.remote.dashboard["title"], "Beam Copy")
                self.assertEqual(len(self.remote.config["views"]), 2 if whole else 1)
                self.assertEqual((self.remote.creates, self.remote.writes), (1, 1))

    @synchronous_test
    async def test_occupied_new_destination_is_not_overwritten(self):
        self.rule.update(creation={"view": True})
        with self.assertRaisesRegex(sync.BeamError, "already contains"):
            await self.run_rule()
        self.assertEqual(self.remote.writes, 0)

    @synchronous_test
    async def test_retry_after_dashboard_registration_reuses_its_id(self):
        self.remote.config = None
        self.remote.dashboard = {"id": "new-id", "url_path": "house"}
        self.state["created_dashboard"] = "new-id"
        self.rule["creation"] = {"dashboard_title": "Beam Copy"}
        await self.run_rule()
        self.assertEqual((self.remote.creates, self.remote.writes), (0, 1))

    @synchronous_test
    async def test_event_stream_checks_only_the_selected_dashboard(self):
        class FakeSocket:
            async def send_json(self, packet):
                self.sent = packet

            async def receive_json(self):
                return {"id": 1, "success": True}

            async def __aiter__(self):
                for event_id, path in ((1, "other"), (2, "house"), (1, "house")):
                    yield SimpleNamespace(type="text", json=lambda: {
                        "id": event_id, "type": "event", "event": {"data": {"url_path": path}}
                    })

        socket = FakeSocket()
        connection = client.Connection(None, socket)
        calls = []
        with patch.dict(sys.modules, {"aiohttp": SimpleNamespace(WSMsgType=SimpleNamespace(TEXT="text"))}), \
                patch.object(client.asyncio, "timeout", lambda _: NoTimeout()):
            await connection.watch_dashboard("house", lambda: calls.append("check"))
        self.assertEqual(calls, ["check", "check"])
        self.assertEqual(socket.sent["event_type"], "lovelace_updated")


class NoTimeout:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False
