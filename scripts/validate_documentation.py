"""Validate DOC-001 pairing, metadata and reciprocal local links."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "custom_components/dashboard_beam/manifest.json").read_text())["version"]
DIRECTORIES = {"human": ROOT / "docs/guides", "ai": ROOT / "docs/ai"}
SLUGS = {kind: {file.stem for file in directory.glob("*.md")}
         for kind, directory in DIRECTORIES.items()}
if not SLUGS["human"] or SLUGS["human"] != SLUGS["ai"]:
    raise SystemExit(f"DOC-001: unpaired manuals: {SLUGS}")

for slug in sorted(SLUGS["human"]):
    for kind, directory in DIRECTORIES.items():
        source = directory / f"{slug}.md"
        content = source.read_text(encoding="utf-8")
        metadata = f"<!-- JTS-DOC: {kind}; slug: {slug}; status: draft; version: {VERSION} -->"
        companion = "ai" if kind == "human" else "guides"
        if not content.startswith(metadata + "\n") or f"(../{companion}/{slug}.md)" not in content:
            raise SystemExit(f"DOC-001: invalid metadata or companion link in {source.name}")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if not target.startswith(("https://", "http://", "#")):
                if not (source.parent / target.partition("#")[0]).is_file():
                    raise SystemExit(f"DOC-001: broken link {target} in {source.name}")

print(f"DOC-001: {len(SLUGS['human'])} manual pair(s), v{VERSION} draft")
