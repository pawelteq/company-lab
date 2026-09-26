"""Publish the credit and leverage study to the frontend."""
import argparse
import json
import shutil
from pathlib import Path

from scripts.publish_leverage_study import latest_collection_id
from etl.config import ROOT


def publish(folder: Path | None = None):
    if folder is None:
        # Pick latest directory in data/research/credit_study
        base = ROOT / "data" / "research" / "credit_study"
        runs = sorted(base.glob("*/results.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not runs:
            raise FileNotFoundError("Nie znaleziono wyników badania credit_study.")
        folder = runs[0].parent

    result = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    destination = ROOT / "frontend" / "public" / "research"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(folder / "results.json", destination / "credit-study-latest.json")
    print(f"Published credit study {result['run_id']} to {destination / 'credit-study-latest.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", nargs="?", type=Path, default=None)
    publish(parser.parse_args().folder)
