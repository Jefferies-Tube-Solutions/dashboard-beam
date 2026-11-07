# Operations Log

## v0.1.0-beta.2

- Pair one editable dashboard or a view per rule, including positional views such as `/0`. Provision a new destination dashboard or append a view during the first valid sync.
- Check both sides on startup and when a configured dashboard is saved, with a five-minute fallback.
- Translate entity IDs and copy PNG, JPEG and GIF assets from supported local image references.
- Block conflicting edits and report failed rules through persistent notifications and a problem sensor.
- Use the source dashboard as the integration entry title and show the selected scope and destination on the service row.
- Use native access for existing local dashboards and reuse a selected Remote Home-Assistant connection, with a documented manual token fallback.
