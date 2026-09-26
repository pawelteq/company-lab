"""Build or verify the local, compressed SQLite profile database."""
from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.local_profiles import build_database, database_path, latest_collection_dir, status
from backend.financial_map import build_index as build_financial_map, index_path as financial_map_path, status as financial_map_status


def main() -> None:
    parser = argparse.ArgumentParser(description="Lokalna baza SQLite dla Company Lab")
    parser.add_argument("command", choices=("build", "status"), nargs="?", default="build")
    parser.add_argument("--collection", type=Path, help="Katalog konkretnego zbioru data/profiles/<id>")
    parser.add_argument("--target", type=Path, help="Ścieżka wynikowej bazy SQLite")
    args = parser.parse_args()
    if args.command == "status":
        result = {"profiles": status()}
        try:
            result["financial_map"] = financial_map_status()
        except (FileNotFoundError, OSError):
            result["financial_map"] = {"ready": False, "path": str(financial_map_path())}
    else:
        source = args.collection.resolve() if args.collection else latest_collection_dir()
        profile_target = args.target.resolve() if args.target else database_path()
        result = {"profiles": build_database(source, profile_target)}
        map_target = profile_target.with_name("financial_map.sqlite3")
        result["financial_map"] = build_financial_map(profile_target, map_target)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
