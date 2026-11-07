"""Synthetic end-to-end reconciliation tests without a Home Assistant runtime."""

from copy import deepcopy
import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest

PACKAGE = "beam_under_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "dashboard_beam")]
sys.modules[PACKAGE] = package
sync = importlib.import_module(f"{PACKAGE}.sync")


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

    async def read(self, path):
        return deepcopy(self.config)

    async def call(self, command, **params):
        if command == "get_states":
            return [{"entity_id": self.entity}]
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
