"""Checks the SPA before upload: every JSON file parses, config.json exists, every lesson in the index has content."""
import json
import pathlib
import sys

web = pathlib.Path(__file__).resolve().parent.parent / "web"
for f in web.rglob("*.json"):
    json.loads(f.read_text())
if not (web / "config.json").exists():
    sys.exit("web/config.json is missing: run tools/seed.py first")
lessons = json.loads((web / "data/lessons/lessons.json").read_text())
for x in json.loads((web / "data/lessons/index.json").read_text()):
    assert x["id"] in lessons, x["id"]
for i in range(1, 6):
    assert (web / f"diagram/page-{i}.png").exists(), f"diagram page {i}"
print("web ok:", sum(1 for _ in web.rglob("*") if _.is_file()), "files")
