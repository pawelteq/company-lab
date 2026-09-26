"""Import and export portable Company Lab data ZIP archives.

The Git repository intentionally contains no company data.  This module moves
the serving SQLite databases, published reports and reproducible analysis
artifacts in a versioned, checksummed archive.  It can also accept a ZIP
containing the provider's raw ``profiles`` bundle and rebuild the databases.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
import argparse
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.config import ROOT


FORMAT = "company-lab-portable-data-v2"
SUPPORTED_FORMATS = {FORMAT, "company-lab-portable-data-v1"}
DATABASE_FILES = {
    "database/company_lab.sqlite3": "company_lab.sqlite3",
    "database/financial_map.sqlite3": "financial_map.sqlite3",
}
ASSET_ROOTS = {
    "assets/published-research": Path("frontend/public/research"),
    "assets/research-history": Path("data/research"),
    "assets/classification": Path("data/classification"),
}


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _snapshot(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Brak bazy danych: {source}")
    source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as reader:
        with closing(sqlite3.connect(target)) as writer:
            reader.backup(writer)
            if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"Baza {source.name} nie przeszła kontroli integralności")


def _database_summary(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    with closing(sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("profile_collection", "profile_screening", "company_verification"):
            if table in tables:
                result[table] = int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
    return result


def export_bundle(
    output: Path,
    *,
    data_dir: Path | None = None,
    project_root: Path | None = None,
) -> dict:
    data_dir = (data_dir or ROOT / ".local").resolve()
    project_root = (project_root or ROOT).resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Plik już istnieje: {output}")

    with tempfile.TemporaryDirectory(prefix="company-lab-export-") as temporary_name:
        temporary = Path(temporary_name)
        files = []
        staged_sources: dict[str, Path] = {}
        summary: dict[str, int] = {}
        for archive_name, filename in DATABASE_FILES.items():
            snapshot = temporary / archive_name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            _snapshot(data_dir / filename, snapshot)
            if filename == "company_lab.sqlite3":
                summary.update(_database_summary(snapshot))
            files.append({
                "path": archive_name,
                "bytes": snapshot.stat().st_size,
                "sha256": _digest(snapshot),
                "kind": "database",
            })
            staged_sources[archive_name] = snapshot

        asset_counts: dict[str, int] = {}
        for archive_root, relative_root in ASSET_ROOTS.items():
            source_root = project_root / relative_root
            count = 0
            if source_root.is_dir():
                for source in sorted(source_root.rglob("*")):
                    if not source.is_file() or source.is_symlink() or source.name == ".gitkeep":
                        continue
                    relative = source.relative_to(source_root).as_posix()
                    archive_name = f"{archive_root}/{relative}"
                    staged = temporary / archive_name
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, staged)
                    files.append({
                        "path": archive_name,
                        "bytes": staged.stat().st_size,
                        "sha256": _digest(staged),
                        "kind": "analysis",
                    })
                    staged_sources[archive_name] = staged
                    count += 1
            asset_counts[archive_root] = count
        summary.update({f"files:{key}": value for key, value in asset_counts.items()})
        manifest = {
            "format": FORMAT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "asset_roots": list(ASSET_ROOTS),
            "summary": summary,
            "files": files,
        }
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr("company-lab-data.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr(
                "README.txt",
                "Prywatna paczka danych Company Lab. Importuj ją plikiem IMPORTUJ_DANE_Z_ZIP.bat.\n"
                "Zawiera bazy, opisy i oznaczenia firm oraz gotowe wyniki analiz.\n"
                "Nie publikuj tej paczki w publicznym repozytorium ani bez zgody właściciela danych.\n",
            )
            for item in files:
                archive.write(staged_sources[item["path"]], item["path"])
    return {
        "mode": "portable",
        "path": str(output),
        "bytes": output.stat().st_size,
        "files": len(files),
        "summary": summary,
    }


def _safe_member(info: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    unix_mode = info.external_attr >> 16
    first_part = path.parts[0] if path.parts else ""
    return (
        bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and ":" not in first_part
        and not (unix_mode and stat.S_ISLNK(unix_mode))
    )


def _backup_state(
    data_dir: Path,
    *,
    project_root: Path | None = None,
    asset_roots: list[str] | None = None,
) -> Path | None:
    existing = [data_dir / filename for filename in DATABASE_FILES.values() if (data_dir / filename).is_file()]
    existing_assets: list[tuple[Path, Path]] = []
    if project_root:
        for archive_root in asset_roots or []:
            relative = ASSET_ROOTS[archive_root]
            source = project_root / relative
            if source.is_dir():
                existing_assets.append((source, relative))
    if not existing and not existing_assets:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = data_dir / "backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    for source in existing:
        shutil.copy2(source, backup_dir / source.name)
    for source, relative in existing_assets:
        shutil.copytree(source, backup_dir / "project" / relative)
    return backup_dir


def _validate_database(path: Path, required_tables: set[str]) -> None:
    with closing(sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"Uszkodzona baza w paczce: {path.name}")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = required_tables - tables
    if missing:
        raise ValueError(f"{path.name}: brak wymaganych tabel: {', '.join(sorted(missing))}")


def import_bundle(
    archive_path: Path,
    *,
    data_dir: Path | None = None,
    project_root: Path | None = None,
) -> dict:
    archive_path = archive_path.resolve()
    data_dir = (data_dir or ROOT / ".local").resolve()
    project_root = (project_root or ROOT).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        if any(not _safe_member(item) for item in archive.infolist()):
            raise ValueError("ZIP zawiera niedozwoloną ścieżkę")
        try:
            manifest = json.loads(archive.read("company-lab-data.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("To nie jest przenośna paczka danych Company Lab") from exc
        if manifest.get("format") not in SUPPORTED_FORMATS:
            raise ValueError(f"Nieobsługiwany format paczki: {manifest.get('format')}")
        declared_items = manifest.get("files", [])
        declared = {item.get("path"): item for item in declared_items}
        if len(declared) != len(declared_items) or None in declared:
            raise ValueError("Manifest zawiera powtórzone lub puste ścieżki")
        if set(DATABASE_FILES) - set(declared):
            raise ValueError("Paczka nie zawiera obu wymaganych baz danych")
        asset_roots = manifest.get("asset_roots", [])
        if any(root not in ASSET_ROOTS for root in asset_roots):
            raise ValueError("Manifest zawiera nieobsługiwany katalog danych")
        allowed_paths = set(DATABASE_FILES)
        for path in declared:
            if path in allowed_paths:
                continue
            if not any(path.startswith(f"{root}/") for root in asset_roots):
                raise ValueError(f"Manifest zawiera niedozwolony plik: {path}")

        required_space = sum(int(item.get("bytes", 0)) for item in declared_items)
        if required_space > shutil.disk_usage(data_dir).free * 0.8:
            raise ValueError("Za mało miejsca na bezpieczny import paczki")

        with tempfile.TemporaryDirectory(prefix="company-lab-import-", dir=data_dir) as temporary_name:
            temporary = Path(temporary_name)
            staged: dict[str, Path] = {}
            for archive_name, expected in declared.items():
                info = archive.getinfo(archive_name)
                if info.file_size != expected.get("bytes"):
                    raise ValueError(f"Nieprawidłowy rozmiar pliku {archive_name}")
                target = temporary / archive_name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                if _digest(target) != expected.get("sha256"):
                    raise ValueError(f"Suma kontrolna pliku {archive_name} nie zgadza się")
                staged[archive_name] = target

            _validate_database(staged["database/company_lab.sqlite3"], {"profile_collection", "profile_screening"})
            _validate_database(staged["database/financial_map.sqlite3"], {"meta", "company", "observation"})

            backup_dir = _backup_state(data_dir, project_root=project_root, asset_roots=asset_roots)
            for archive_name, filename in DATABASE_FILES.items():
                os.replace(staged[archive_name], data_dir / filename)
            installed_assets = []
            for archive_root in asset_roots:
                target = project_root / ASSET_ROOTS[archive_root]
                if target.exists():
                    shutil.rmtree(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                staged_root = temporary / archive_root
                if staged_root.is_dir():
                    shutil.move(str(staged_root), str(target))
                else:
                    target.mkdir(parents=True, exist_ok=True)
                installed_assets.append(str(target))

            published_root = "assets/published-research"
            if published_root in asset_roots and (project_root / "frontend/dist").is_dir():
                public_research = project_root / ASSET_ROOTS[published_root]
                dist_research = project_root / "frontend/dist/research"
                if dist_research.exists():
                    shutil.rmtree(dist_research)
                shutil.copytree(public_research, dist_research)

    return {
        "mode": "portable", "archive": str(archive_path),
        "installed": [str(data_dir / filename) for filename in DATABASE_FILES.values()],
        "installed_assets": installed_assets,
        "summary": manifest.get("summary", {}),
        "backup": str(backup_dir) if backup_dir else None,
    }


def _extract_raw(archive_path: Path, target: Path) -> Path:
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if any(not _safe_member(item) for item in infos):
            raise ValueError("ZIP zawiera niedozwoloną ścieżkę")
        free = shutil.disk_usage(target).free
        expanded = sum(item.file_size for item in infos)
        if expanded > free * 0.8:
            raise ValueError("Za mało miejsca na bezpieczne rozpakowanie ZIP-a")
        archive.extractall(target)
    candidates = [folder for folder in target.rglob("profiles") if folder.is_dir() and next(folder.glob("*.json"), None)]
    if not candidates:
        raise ValueError("ZIP nie zawiera katalogu profiles z plikami JSON")
    return max(candidates, key=lambda folder: sum(1 for _ in folder.glob("*.json")))


def import_archive(
    archive_path: Path,
    *,
    data_dir: Path | None = None,
    project_root: Path | None = None,
) -> dict:
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        if "company-lab-data.json" in archive.namelist():
            return import_bundle(archive_path, data_dir=data_dir, project_root=project_root)

    work_root = (data_dir or ROOT / ".local").resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    backup_dir = _backup_state(work_root)
    with tempfile.TemporaryDirectory(prefix="company-lab-raw-", dir=work_root) as temporary_name:
        profiles = _extract_raw(archive_path, Path(temporary_name))
        from scripts.import_profiles import run
        run(profiles)
    from backend.financial_map import build_index
    result = build_index()
    return {
        "mode": "raw",
        "archive": str(archive_path),
        "financial_map": result,
        "backup": str(backup_dir) if backup_dir else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Przenoszenie pełnych danych Company Lab w ZIP")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="Utwórz przenośną paczkę danych")
    export_parser.add_argument("output", type=Path)
    import_parser = subparsers.add_parser("import", help="Zaimportuj paczkę przenośną lub surowe dane")
    import_parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    result = export_bundle(args.output) if args.command == "export" else import_archive(args.archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
