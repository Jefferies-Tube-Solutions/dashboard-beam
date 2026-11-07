<!-- JTS-DOC: ai; slug: replication; status: draft; version: 0.1.0-beta.1 -->
# AI Systems Reference — Dashboard replication

Companion: [Human Operations Manual](../guides/replication.md)

## Configuration contract

Each config entry stores two editable dashboard URL paths (`local_dashboard`, `remote_dashboard`), two view paths (`local_view`, `remote_view`, both empty for whole-dashboard sync), and `initial_source` (0 local, 1 remote). Manual remote access stores `remote_url`, `remote_token` and the normalized `prefix`. Reused access stores `remote_entry_id` and setup-time origin/prefix metadata. It resolves the selected entry's host, port, secure flag, access token and entity prefix at runtime. The remote token is not copied into Beam's entry. Disabled or removed entries block the rule. Prefixes are normalized to lowercase and checked against `[a-z0-9_]*`. Remote access must authenticate as an administrator during setup. TLS certificate checks remain enabled.

Beam reads and saves existing local dashboards through Lovelace storage and reads local entity IDs from the state machine. Local uploads use Home Assistant's image collection. `local_url` and `local_token` are used only to register a new local dashboard through the WebSocket API. Legacy entries with both tokens continue to load. Overlapping scopes in this installation are rejected.

An existing view uses its explicit path or its zero-based index as a string. `creation` is absent for existing pairs, `{"view": true}` to append a view, or `{"dashboard_title": "..."}` to create a storage dashboard. The destination is the opposite side from `initial_source`. A new view path must be a nonnumeric lowercase slug. A new dashboard path must contain a hyphen. Existing config entries keep their stored paths.

New entries use the source dashboard title as the config entry title. Optional `service_name` stores the selected source scope, destination dashboard title and destination scope as a display string. Existing entries without it use their entry title.

## Execution and observability

- Startup, a 300-second fallback timer, and `lovelace_updated` events matching either configured dashboard path request reconciliation. The local event bus and a separate remote WebSocket subscription feed the same coalescing trigger. Remote subscription establishment requests a check, and disconnects retry after 30 seconds. The shared lock serializes writes across entries. Unload cancels the remote subscription and reconciliation task.
- The persistent comparison baseline uses sorted JSON SHA-256 after mapping entity IDs and supported local image content hashes. Equal configs establish a baseline. Divergent uninitialized pairs use the selected initial source. One changed side transfers. Two divergent changes block.
- Structured `entity`, `entity_id` and `entities` values and recognized IDs in common template delimiters are mapped. The sending rule requires both expected state IDs. Missing IDs produce a location in the notification.
- `image`, `background`, `state_image` and `dark_image` support HA uploaded images and PNG/JPEG/GIF `/local/` assets up to 9 MiB. The destination uses HA image upload. Shared external URLs stay literal. Replication can create image objects before a dashboard write.
- The selected view is replaced by its effective URL path within the latest read dashboard. Positional views remain pathless, and sibling views are preserved. Both full configurations are re-read before the save. Lovelace has no compare-and-swap, so an external save in the final read/write gap can race.
- Provisioning happens only before the first baseline, after source validation. A new dashboard is registered with `lovelace/dashboards/create` and its ID is saved before writing dashboard content. A new view is appended. Beam rejects an occupied destination and uses the pending content hash to recognize a successful write after an interrupted baseline save. If dashboard registration succeeded before its ID could be stored, the operator must resolve the occupied path manually. Deleting a previously synced target blocks the rule.
- The problem sensor reports `on` with `reason` when blocked, `off` after a successful check and unavailable before the first check. The integration creates one persistent notification per failed entry and dismisses it on recovery.

## Boundaries and verification

No conflict merge, image cleanup, custom card installation, device/area ID translation, or arbitrary template analysis in Beta 1. Both instances must be able to serve their own assets. Local image URLs are restricted to known HA paths. Network, event delivery and setup compatibility still require live HA commissioning. See [synthetic tests](../../tests/test_sync.py) for the comparison contract.
