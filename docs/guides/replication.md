<!-- JTS-DOC: human; slug: replication; status: draft; version: 0.1.0 -->
# Human Operations Manual — Dashboard replication

Companion: [AI Systems Reference](../ai/replication.md)

## Commissioning

1. Use two reachable Home Assistant 2026.11 instances and two administrator long-lived access tokens. Enter the tokens only in the Home Assistant setup dialog.
2. Copy `custom_components/dashboard_beam` to the local instance's `custom_components` folder and restart it. Install Beam on the local instance alone.
3. Open **Settings → Devices & services → Add integration → JTS - Dashboard Beam**. Enter both HA origins and the local entity prefix, including its separator. For example, use `cabin_` when remote `light.porch` appears locally as `light.cabin_porch`. Beam suggests a prefix when configured Remote Home Assistant entries agree on one nonempty value.
4. Select an editable dashboard on both sides. Choose the whole dashboard or one existing view with an explicit path on each side. Create any destination view in HA before configuring Beam.
5. Choose the initial source. The first automatic check copies that version if the content differs. Add another integration entry for another pair.

## Verification and recovery

Save a change to a card on either side. Beam requests a check when Home Assistant reports the dashboard save. Allow up to five minutes for the fallback check if the event was missed. Verify the corresponding view and its picture. Use the service's **Replication problem** entity as an optional conditional dashboard badge, visible when on. The persistent notification gives the failure reason, including the missing entity and its location in the configuration when detected.

Restore missing entities or repair the connection and wait for the next check. If both sides changed, bring the pair to the same intended content manually to resume. To roll back, disable the rule before restoring a dashboard backup. Removing an entry removes Beam's saved comparison state. Dashboard and image backups are the operator's responsibility.

Storage dashboards with explicit view paths are the test target. Review navigation links, device and area IDs, installed custom cards and template-generated entity references before use across sites. The draft is awaiting live verification.
