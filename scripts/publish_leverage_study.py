"""Publish a completed, collection-matched aggregate study to the local frontend."""
import argparse
import json
import shutil
from pathlib import Path

from backend.app import connection
from backend.local_profiles import available as local_database_available
from backend.local_profiles import connect as local_connection
from etl.config import ROOT


def latest_collection_id() -> str:
    if not local_database_available():
        with connection() as conn:
            return str(conn.execute('SELECT id FROM core.profile_collection ORDER BY created_at DESC,id DESC LIMIT 1').fetchone()['id'])
    else:
        with local_connection() as conn:
            return str(conn.execute('SELECT id FROM profile_collection ORDER BY created_at DESC,id DESC LIMIT 1').fetchone()['id'])


def publish(folder: Path):
    result = json.loads((folder / 'results.json').read_text(encoding='utf-8'))
    latest = latest_collection_id()
    if result['collection_id'] != latest:
        raise ValueError('Study belongs to an older collection; calculate the current collection first.')
    if not result.get('models') or not result.get('audit', {}).get('selected_companies'):
        raise ValueError('Study is incomplete.')
    destination = ROOT / 'frontend/public/research'
    destination.mkdir(parents=True, exist_ok=True)
    # Deliberately publish aggregates only, never the firm-level panel or selection.
    shutil.copyfile(folder / 'results.json', destination / 'leverage-latest.json')
    shutil.copyfile(folder / 'report.md', destination / 'leverage-report.md')
    print(f"Published {result['run_id']}; rebuild frontend to include the study.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    publish(parser.parse_args().folder)
