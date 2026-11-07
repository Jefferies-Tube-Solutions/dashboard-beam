<!-- JTS-DOC: human; slug: replication; status: draft; version: 0.1.0-beta.1 -->
# Human Operations Manual — Dashboard replication

Companion: [AI Systems Reference](../ai/replication.md)

## Commissioning

1. Use two reachable Home Assistant 2026.11 instances and two administrator long-lived access tokens. Enter the tokens only in the Home Assistant setup dialog.
2. On the local instance, add `https://github.com/Jefferies-Tube-Solutions/dashboard-beam` to **Settings → Marketplace** as a custom integration, enable prereleases and install **v0.1.0-beta.1**. Restart if prompted.
3. Open **Settings → Devices & services → Add integration → JTS - Dashboard Beam**. Enter both HA origins and the local entity prefix, including its separator. For example, use `cabin_` when remote `light.porch` appears locally as `light.cabin_porch`. Beam suggests a prefix when configured Remote Home Assistant entries agree on one nonempty value.
4. Choose the source site, dashboard and scope. Select **Entire dashboard** or one view or subview. A view without a configured path appears with its positional URL, such as `/0`.
5. Choose an existing destination dashboard or create a new one. For a single-view rule, select a destination view or enter a path for a new view. A new dashboard starts with administrator-only access and can receive either the whole source dashboard or just the selected view. A new view inherits the source view's content and title, if present.
6. The first valid check copies from the selected source and creates the destination if requested. Afterward the rule synchronizes in both directions. Add another integration entry for another pair.

The integration entry is named after the source dashboard. Its service row shows the selected view or **All views**, followed by the destination dashboard and scope. Each view pair has its own rule.

## Verification and recovery

Save a change to a card on either side. Beam requests a check when Home Assistant reports the dashboard save. Allow up to five minutes for the fallback check if the event was missed. Verify the corresponding view and its picture. Use the service's **Replication problem** entity as an optional conditional dashboard badge, visible when on. The persistent notification gives the failure reason, including the missing entity and its location in the configuration when detected.

Restore missing entities or repair the connection and wait for the next check. If both sides changed, bring the pair to the same intended content manually to resume. To roll back, disable the rule before restoring a dashboard backup. Removing an entry removes Beam's saved comparison state. Dashboard and image backups are the operator's responsibility.

Positional URLs follow the order of the views. If you rearrange views, verify that a rule using a positional URL still points to the intended view. Review navigation links, device and area IDs, installed custom cards and template-generated entity references before use across sites. The draft is awaiting live verification.
