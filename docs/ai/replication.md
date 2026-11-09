<!-- JTS-DOC: ai; slug: replication; status: stable; version: 1.0.0 -->
# AI Systems Reference — Dashboard replication

Companion: [Human Operations Manual](../guides/replication.md)

## Configuration contract

Each config entry stores two editable dashboard URL paths (`local_dashboard`, `remote_dashboard`), two view paths (`local_view`, `remote_view`, both empty for whole-dashboard sync), and `initial_source` (0 local, 1 remote). Manual remote access stores `remote_url`, `remote_token` and the normalized `prefix`. Reused access stores `remote_entry_id` and setup-time origin/prefix metadata. It resolves the selected entry's host, port, secure flag, access token and entity prefix at runtime. The remote token is not copied into Beam's entry. Disabled or removed entries block the rule. Prefixes are normalized to lowercase and checked against `[a-z0-9_]*`. Remote access must authenticate as an administrator during setup. TLS certificate checks remain enabled.

Beam reads and saves existing local dashboards through Lovelace storage and reads local entity IDs from the state machine. Local uploads use Home Assistant's image collection. `local_url` and `local_token` are used only to register a new local dashboard through the WebSocket API. Legacy entries with both tokens continue to load. Overlapping scopes in this installation are rejected.

An existing view uses its explicit path or its zero-based index as a string. `creation` is absent for existing pairs, `{"view": true, "view_title": "..."}` to append a named view, or `{"dashboard_title": "..."}` to create a storage dashboard. The destination is the opposite side from `initial_source`. The UI accepts a name and derives a lowercase route, adding a suffix for known collisions. A single view copied into a new dashboard derives its route from the source route. For named view creation, each side retains its own view title during later synchronization. Existing config entries keep their stored paths and title behavior.

New entries use the source dashboard title as the config entry title. Optional `service_name` stores the selected source scope, destination dashboard title and destination scope as a display string. Existing entries without it use their entry title.

## Execution and observability

- Startup, a 300-second fallback timer, and `lovelace_updated` events matching either configured dashboard path request reconciliation. The local event bus and a separate remote WebSocket subscription feed the same coalescing trigger. Remote subscription establishment requests a check, and disconnects retry after 30 seconds. The shared lock serializes writes across entries. Unload cancels the remote subscription and reconciliation task.
- The persistent comparison baseline uses sorted JSON SHA-256 after mapping entity IDs and supported local image content hashes. Equal configs establish a baseline. Divergent uninitialized pairs use the selected initial source. One changed side transfers. Two divergent changes block.
- Structured `entity`, `entity_id` and `entities` values and recognized IDs in common template delimiters are mapped. The sending rule requires both expected state IDs. Missing IDs produce a location in the notification.
- Image fields include `dark_mode_image` and accept HA uploaded images, `/local/` assets and `media-source://media_source/<directory>/<file>` references, including image objects with `media_content_id`. Local media is read within the configured media directory. Remote media uses an authenticated request to the configured HA origin. Beam copies PNG, JPEG and GIF files up to 9 MiB into the destination image store and regenerates image references without source-specific metadata.
- The selected view is replaced by its effective URL path, preserving sibling views and an absent `path`. Positional rules record surrounding explicit paths or hashes of pathless siblings. A changed surrounding layout blocks writes. Existing positional rules without a recorded layout must match the prior baseline on that side before Beam trusts the position. Both configurations are re-read before the save. Lovelace has no compare-and-swap, so a save in the final read/write gap can race.
- Provisioning happens only before the first baseline, after source validation. A new dashboard is registered with `lovelace/dashboards/create` and its ID is saved before writing dashboard content. A new view is appended. Beam rejects an occupied destination and uses the pending content hash to recognize a successful write after an interrupted baseline save. If dashboard registration succeeded before its ID could be stored, the operator must resolve the occupied path manually. Deleting a previously synced target blocks the rule.
- The problem sensor reports `on` with `reason` when blocked, `off` after a successful check and unavailable before the first check. The integration creates one persistent notification per failed entry and dismisses it on recovery.

## Boundaries and verification

No conflict merge, image cleanup, custom card installation, device/area ID translation, or arbitrary template analysis in v1.0.0. Both instances must be able to serve their own assets. Local image URLs are restricted to known HA paths. Two-instance QA verified the release candidate for initial image transfer, reverse edits, and blocking and recovery when positional views were reordered. See [synthetic tests](../../tests/test_sync.py) for the comparison contract.
