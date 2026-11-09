<!-- JTS-DOC: human; slug: replication; status: draft; version: 1.0.0-beta.1 -->
# Human Operations Manual — Dashboard replication

Companion: [AI Systems Reference](../ai/replication.md)

## Commissioning

1. Use two reachable Home Assistant 2026.11 instances. Beam reads local dashboards and entity states directly.
2. On the local instance, add `https://github.com/Jefferies-Tube-Solutions/dashboard-beam` to **Settings → Marketplace** as a custom integration, enable prereleases and install **v1.0.0-beta.1**. Restart if prompted.
3. Open **Settings → Devices & services → Add integration → JTS - Dashboard Beam**. Select the existing **Remote Home-Assistant** connection if available. Beam reads its address, token and entity prefix. If the connection uses a nonadministrator account, choose manual access. On the remote instance, open the administrator profile → **Security → Long-lived access tokens → Create token**. Enter the token and remote base URL in the Beam dialog. Add the entity prefix if used.
4. Choose the source site, dashboard and scope. Select **Entire dashboard** or one view or subview. A view without a configured path appears with its positional URL, such as `/0`.
5. Choose an existing destination or create a new one. Enter just the destination name. Beam generates the URL, using a numeric suffix if needed. A new dashboard starts with administrator-only access and can receive either the whole source dashboard or one selected view, which keeps its source title. When creating a view in an existing dashboard, the name you enter becomes that view's title.
6. The first valid check copies from the selected source and creates the destination if requested. Afterward the rule synchronizes in both directions. Add another integration entry for another pair.

The integration entry is named after the source dashboard. Its service row shows the selected view or **All views**, followed by the destination dashboard and scope. Each view pair has its own rule.

Creating a brand-new dashboard on the local instance is the one case that asks for local administrator access. Beam suggests the local URL if Home Assistant has one. Select an existing local dashboard, or create a new view within one, to use the direct local connection.

## Verification and recovery

Save a change to a card on either side. Beam requests a check when Home Assistant reports the dashboard save. Allow up to five minutes for the fallback check if the event was missed. Verify the corresponding view and its picture. Use the service's **Replication problem** entity as an optional conditional dashboard badge, visible when on. The persistent notification gives the failure reason, including the missing entity and its location in the configuration when detected.

Restore missing entities or repair the connection and wait for the next check. If both sides changed, bring the pair to the same intended content manually to resume. To roll back, disable the rule before restoring a dashboard backup. Removing an entry removes Beam's saved comparison state. Dashboard and image backups are the operator's responsibility.

Positional URLs follow the order of the views. If you rearrange views, verify that a rule using a positional URL still points to the intended view. Review navigation links, device and area IDs, installed custom cards and template-generated entity references before use across sites. The draft is awaiting live verification.
