"""Consistent SQLite backup through stdlib; safe while the dashboard is running."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Backup Agentboard database without credentials')
parser.add_argument('destination', type=Path)
parser.add_argument('--data-dir', type=Path, default=root / 'data')
args = parser.parse_args()
source = (args.data_dir / 'agentboard.sqlite3').resolve()
destination = args.destination.resolve()
if not source.is_file():
    parser.error('Database does not exist; start the dashboard first')
if source == destination or destination.exists():
    parser.error('Choose a NEW destination file; existing files are not overwritten')
destination.parent.mkdir(parents=True, exist_ok=True)
with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
    with closing(sqlite3.connect(destination)) as backup:
        original.backup(backup)
        if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed')
print(f'Backup verified: {destination}')
