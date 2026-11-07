"""Validate DOC-001 pairing, metadata and reciprocal local links."""

import hashlib
import json
import re
from pathlib import Path

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

readme = (ROOT / "README.md").read_text(encoding="utf-8")
expected_images = (
    "docs/brand/jts-white-transparent.png#gh-dark-mode-only",
    "docs/brand/jts-deep-space-transparent.png#gh-light-mode-only",
    "custom_components/dashboard_beam/brand/icon.png",
)
if not readme.startswith('<p align="right">') or f'alt="draft | v{VERSION}"' not in readme:
    raise SystemExit("VIS-002: README must show the current draft version.")
images = tuple(re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', readme.partition("</p>")[2]))
if images[:3] != expected_images:
    raise SystemExit("VIS-001: README must show the approved theme and product artwork.")
for slug in SLUGS["human"]:
    for folder in ("guides", "ai"):
        if f"](docs/{folder}/{slug}.md)" not in readme:
            raise SystemExit(f"DOC-001: README is missing the {folder}/{slug} manual.")
provenance = json.loads((ROOT / "docs/brand/provenance.json").read_text(encoding="utf-8"))
registered = {item["path"]: item["sha256"] for item in provenance["files"]}
if not {image.split("#")[0] for image in expected_images} <= registered.keys():
    raise SystemExit("VIS-001: README artwork must have recorded provenance.")
for path, expected_hash in registered.items():
    actual_hash = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise SystemExit(f"VIS-001: artwork differs from the recorded export: {path}")
print("VIS-001–002: README and registered artwork verified")
