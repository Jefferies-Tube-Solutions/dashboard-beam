# JTS Engineering Command

This repository follows the [JTS Brand System v1.1.0](https://github.com/Jefferies-Tube-Solutions/jts-brand-system/tree/v1.1.0). Read its standing orders and applicable standards before changing product identity, documentation, configuration or runtime behavior.

- DOC-001 requires reciprocal human and AI manuals with matching slugs, status and version. Update them with any change to behavior or commissioning. Explain documentation-neutral changes in review.
- VIS-001 requires the theme-aware JTS publisher art and a separate product hex. Preserve the recorded artwork provenance and current draft status.
- HA-001 and HA-002 govern Home Assistant compatibility, HACS validation and service identity. Run the repository tests, documentation check, hassfest and HACS validation before commissioning.
- Keep change history in the Operations Log. Public docs and code use English. State which checks used synthetic data and which ran against a live Home Assistant instance.

For visual changes, check rendered light and dark themes and mobile views. Record
what was verified in the pull request. The required `JTS documentation` job runs the [shared JTS check](https://github.com/Jefferies-Tube-Solutions/jts-brand-checks) pinned in `.github/workflows/validate.yml`. It checks README status, approved artwork and paired manuals before merging.
