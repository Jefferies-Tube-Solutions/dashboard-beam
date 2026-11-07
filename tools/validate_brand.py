"""Check the repository's current JTS brand adoption baseline."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
errors = []
if "## JTS Brand System" not in AGENTS or "jts-brand-system" not in AGENTS:
    errors.append("AGENTS.md must reference the JTS Brand System policy.")

if "**Status:** Draft" not in README or "## Mission Directive" not in README:
    errors.append("Draft README must disclose its status and mission.")
if "**Product artwork:** Pending approval." not in README or re.search(
    r"<img\b|!\[", README, re.IGNORECASE
):
    errors.append("Use the pending artwork notice until approved exports are adopted.")

if errors:
    raise SystemExit("\n".join(errors))
print("JTS adoption baseline passed.")
