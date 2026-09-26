"""Import and export portable Company Lab data ZIP archives.

The Git repository intentionally contains no company data.  This module moves
the two serving SQLite databases in a versioned, checksummed archive, or accepts
a ZIP containing the provider's raw ``profiles`` bundle and rebuilds them.
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


FORMAT = "company-lab-portable-data-v1"
DATABASE_FILES = {
    "database/company_lab.sqlite3": "company_lab.sqlite3",
    "database/financial_map.sqlite3": "financial_map.sqlite3",
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


def export_bundle(output: Path, *, data_dir: Path | None = None) -> dict:
    data_dir = (data_dir or ROOT / ".local").resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Plik już istnieje: {output}")

    with tempfile.TemporaryDirectory(prefix="company-lab-export-") as temporary_name:
        temporary = Path(temporary_name)
        files = []
        for archive_name, filename in DATABASE_FILES.items():
            snapshot = temporary / filename
            _snapshot(data_dir / filename, snapshot)
            files.append({
                "path": archive_name,
                "bytes": snapshot.stat().st_size,
                "sha256": _digest(snapshot),
            })
        manifest = {
            "format": FORMAT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
        }
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr("company-lab-data.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr(
                "README.txt",
                "Prywatna paczka danych Company Lab. Importuj ją plikiem IMPORTUJ_DANE_Z_ZIP.bat.\n"
                "Nie publikuj tej paczki w publicznym repozytorium ani bez zgody właściciela danych.\n",
            )
            for item in files:
                archive.write(temporary / Path(item["path"]).name, item["path"])
    return {"mode": "portable", "path": str(output), "bytes": output.stat().st_size, "files": files}


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


def _backup_databases(data_dir: Path) -> Path | None:
    existing = [data_dir / filename for filename in DATABASE_FILES.values() if (data_dir / filename).is_file()]
    if not existing:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = data_dir / "backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    for source in existing:
        shutil.copy2(source, backup_dir / source.name)
    return backup_dir


def _validate_database(path: Path, required_tables: set[str]) -> None:
    with closing(sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"Uszkodzona baza w paczce: {path.name}")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = required_tables - tables
    if missing:
        raise ValueError(f"{path.name}: brak wymaganych tabel: {', '.join(sorted(missing))}")


def import_bundle(archive_path: Path, *, data_dir: Path | None = None) -> dict:
    archive_path = archive_path.resolve()
    data_dir = (data_dir or ROOT / ".local").resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        if any(not _safe_member(item) for item in archive.infolist()):
            raise ValueError("ZIP zawiera niedozwoloną ścieżkę")
        try:
            manifest = json.loads(archive.read("company-lab-data.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("To nie jest przenośna paczka danych Company Lab") from exc
        if manifest.get("format") != FORMAT:
            raise ValueError(f"Nieobsługiwany format paczki: {manifest.get('format')}")
        declared = {item.get("path"): item for item in manifest.get("files", [])}
        if set(DATABASE_FILES) - set(declared):
            raise ValueError("Paczka nie zawiera obu wymaganych baz danych")

        with tempfile.TemporaryDirectory(prefix="company-lab-import-", dir=data_dir) as temporary_name:
            temporary = Path(temporary_name)
            staged: dict[str, Path] = {}
            for archive_name, filename in DATABASE_FILES.items():
                info = archive.getinfo(archive_name)
                expected = declared[archive_name]
                if info.file_size != expected.get("bytes"):
                    raise ValueError(f"Nieprawidłowy rozmiar pliku {archive_name}")
                target = temporary / filename
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                if _digest(target) != expected.get("sha256"):
                    raise ValueError(f"Suma kontrolna pliku {archive_name} nie zgadza się")
                staged[filename] = target

            _validate_database(staged["company_lab.sqlite3"], {"profile_collection", "profile_screening"})
            _validate_database(staged["financial_map.sqlite3"], {"meta", "company", "observation"})

            backup_dir = _backup_databases(data_dir)
            for filename, source in staged.items():
                os.replace(source, data_dir / filename)

    return {
        "mode": "portable", "archive": str(archive_path),
        "installed": [str(data_dir / filename) for filename in DATABASE_FILES.values()],
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


def import_archive(archive_path: Path, *, data_dir: Path | None = None) -> dict:
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        if "company-lab-data.json" in archive.namelist():
            return import_bundle(archive_path, data_dir=data_dir)

    work_root = (data_dir or ROOT / ".local").resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    backup_dir = _backup_databases(work_root)
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
