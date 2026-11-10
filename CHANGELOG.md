# Operations Log

## v1.0.2

- Show the full transparent Dashboard Beam lockup in the README for light and dark themes.

## v1.0.1

- Reorganize the README around commissioning, verification and recovery.
- Run the shared JTS documentation and artwork check before merging. Codex reviews pull requests using the project's JTS rules.
- Replication behavior is unchanged from v1.0.0.

## v1.0.0

- First stable release. Promotes the tested 1.0 Beta 2 replication behavior.
- Verified on two Home Assistant instances using isolated dashboards. A media-browser image copied to the destination, a return edit propagated, and moving a positional view blocked replication until the order was restored.

## v1.0.0-beta.2

- Block writes when the surrounding dashboard layout can no longer identify a positional view safely.
- Copy images selected through Home Assistant's local media browser, including structured image references.

## v1.0.0-beta.1

- Promote Beta 3 to the first 1.0 approval candidate.

## v0.1.0-beta.3

- Ask only for the new destination name and generate the dashboard and view URL paths automatically.
- Preserve the chosen name of a new view in an existing dashboard during replication.

## v0.1.0-beta.2

- Pair one editable dashboard or a view per rule, including positional views such as `/0`. Provision a new destination dashboard or append a view during the first valid sync.
- Check both sides on startup and when a configured dashboard is saved, with a five-minute fallback.
- Translate entity IDs and copy PNG, JPEG and GIF assets from supported local image references.
- Block conflicting edits and report failed rules through persistent notifications and a problem sensor.
- Use the source dashboard as the integration entry title and show the selected scope and destination on the service row.
- Use native access for existing local dashboards and reuse a selected Remote Home-Assistant connection, with a documented manual token fallback.
