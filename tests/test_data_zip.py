from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from scripts.data_zip import export_bundle, import_bundle


def _database(path: Path, statements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.commit()


def _source_databases(folder: Path, marker: str = "pierwsza") -> None:
    _database(
        folder / "company_lab.sqlite3",
        [
            "CREATE TABLE profile_collection (id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE profile_screening (id INTEGER PRIMARY KEY, result TEXT)",
            f"INSERT INTO profile_collection (name) VALUES ('{marker}')",
        ],
    )
    _database(
        folder / "financial_map.sqlite3",
        [
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE observation (id INTEGER PRIMARY KEY, value REAL)",
            f"INSERT INTO meta (key, value) VALUES ('marker', '{marker}')",
        ],
    )


def test_export_and_import_complete_portable_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _source_databases(source)
    _source_databases(target, marker="stara")
    archive_path = tmp_path / "dane.zip"

    exported = export_bundle(archive_path, data_dir=source)
    imported = import_bundle(archive_path, data_dir=target)

    assert exported["mode"] == "portable"
    assert imported["backup"] is not None
    with closing(sqlite3.connect(target / "company_lab.sqlite3")) as connection:
        assert connection.execute("SELECT name FROM profile_collection").fetchone()[0] == "pierwsza"
    with closing(sqlite3.connect(target / "financial_map.sqlite3")) as connection:
        assert connection.execute("SELECT value FROM meta WHERE key='marker'").fetchone()[0] == "pierwsza"
    backup = Path(imported["backup"])
    with closing(sqlite3.connect(backup / "company_lab.sqlite3")) as connection:
        assert connection.execute("SELECT name FROM profile_collection").fetchone()[0] == "stara"


def test_import_rejects_changed_database(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source_databases(source)
    original = tmp_path / "dane.zip"
    tampered = tmp_path / "zmienione.zip"
    export_bundle(original, data_dir=source)

    with zipfile.ZipFile(original) as reader, zipfile.ZipFile(tampered, "w") as writer:
        for info in reader.infolist():
            contents = reader.read(info)
            if info.filename == "database/company_lab.sqlite3":
                contents += b"zmiana"
            writer.writestr(info, contents)

    with pytest.raises(ValueError, match="rozmiar"):
        import_bundle(tampered, data_dir=tmp_path / "target")


def test_export_manifest_has_version_and_checksums(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source_databases(source)
    archive_path = tmp_path / "dane.zip"
    export_bundle(archive_path, data_dir=source)

    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("company-lab-data.json"))
    assert manifest["format"] == "company-lab-portable-data-v1"
    assert {item["path"] for item in manifest["files"]} == {
        "database/company_lab.sqlite3",
        "database/financial_map.sqlite3",
    }
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])


def test_import_rejects_path_outside_archive(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source_databases(source)
    archive_path = tmp_path / "dane.zip"
    export_bundle(archive_path, data_dir=source)
    with zipfile.ZipFile(archive_path, "a") as archive:
        archive.writestr("../poza-katalogiem.txt", "niebezpieczne")

    with pytest.raises(ValueError, match="niedozwoloną ścieżkę"):
        import_bundle(archive_path, data_dir=tmp_path / "target")
