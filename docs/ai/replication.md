<!-- JTS-DOC: ai; slug: replication; status: draft; version: 0.1.0 -->
# AI Systems Reference — Dashboard replication

Companion: [Human Operations Manual](../guides/replication.md)

## Configuration contract

Each config entry stores two HTTP(S) origin strings (`local_url`, `remote_url`), two administrator token strings (`local_token`, `remote_token`), two editable dashboard URL paths (`local_dashboard`, `remote_dashboard`), two view paths (`local_view`, `remote_view`, both empty for whole-dashboard sync), a local `prefix` matching `[a-z0-9_]*`, and `initial_source` (0 local, 1 remote). Overlapping scopes in this installation are rejected.

## Execution and observability

- Startup, a 300-second fallback timer, and `lovelace_updated` events matching either configured dashboard path request reconciliation. The local event bus and a separate remote WebSocket subscription feed the same coalescing trigger. Remote subscription establishment requests a check, and disconnects retry after 30 seconds. The shared lock serializes writes across entries. Unload cancels the remote subscription and reconciliation task.
- The persistent comparison baseline uses sorted JSON SHA-256 after mapping entity IDs and supported local image content hashes. Equal configs establish a baseline. Divergent uninitialized pairs use the selected initial source. One changed side transfers. Two divergent changes block.
- Structured `entity`, `entity_id` and `entities` values and recognized IDs in common template delimiters are mapped. The sending rule requires both expected state IDs. Missing IDs produce a location in the notification.
- `image`, `background`, `state_image` and `dark_image` support HA uploaded images and PNG/JPEG/GIF `/local/` assets up to 9 MiB. The destination uses HA image upload. Shared external URLs stay literal. Replication can create image objects before a dashboard write.
- The selected view is replaced by path within the latest read dashboard, preserving sibling views. Both full configurations are re-read before the save. Lovelace has no compare-and-swap, so an external save in the final read/write gap can race.
- The problem sensor reports `on` with `reason` when blocked, `off` after a successful check and unavailable before the first check. The integration creates one persistent notification per failed entry and dismisses it on recovery.

## Boundaries and verification

No automatic dashboard or view creation, conflict merge, image cleanup, custom card installation, device/area ID translation, or arbitrary template analysis in v0.1.0. Both instances must be able to serve their own assets. Local image URLs are restricted to known HA paths. Network, event delivery and setup compatibility still require live HA commissioning. See [synthetic tests](../../tests/test_sync.py) for the comparison contract.
