"""Publish the aggregate developer-question study for the current collection."""
import argparse
import json
import shutil
from pathlib import Path

from scripts.publish_leverage_study import latest_collection_id
from etl.config import ROOT


def publish(folder: Path):
    result = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    latest = latest_collection_id()
    if result["collection_id"] != latest:
        raise ValueError("Study belongs to an older collection")
    destination = ROOT / "frontend/public/research"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(folder / "results.json", destination / "developer-questions-latest.json")
    shutil.copyfile(folder / "report.md", destination / "developer-questions-report.md")
    print(f"Published {result['run_id']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    publish(parser.parse_args().folder)
