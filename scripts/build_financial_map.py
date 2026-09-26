"""Build the indexed financial observations used by the Financial Map of Poland."""
from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.financial_map import build_index, index_path, status
from backend.local_profiles import database_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Indeks finansowej mapy Polski")
    parser.add_argument("command", choices=("build", "status"), nargs="?", default="build")
    parser.add_argument("--source", type=Path, help="Źródłowa baza profili SQLite")
    parser.add_argument("--target", type=Path, help="Ścieżka indeksu mapy")
    args = parser.parse_args()
    if args.command == "status":
        result = status()
    else:
        result = build_index(
            args.source.resolve() if args.source else database_path(),
            args.target.resolve() if args.target else index_path(),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
