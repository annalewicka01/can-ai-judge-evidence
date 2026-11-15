"""Offline evidence checks reject drift and resolve historical checkout paths."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('reproduce', ROOT / 'scripts/reproduce.py')
reproduce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reproduce)


def test_historical_paths_are_checkout_relative():
    assert reproduce.relative('/Users/oalw/can-ai-judge-evidence/runs/example.json') == Path('runs/example.json')
    assert reproduce.relative('/Users/oalw/would-we-notice/runs/example.json') == Path('runs/example.json')


def test_table_comparison_preserves_provenance_values(tmp_path):
    saved = tmp_path / 'table.json'
    saved.write_text(json.dumps({'/Users/oalw/would-we-notice/runs/a': 'hash'}))
    reproduce.equal({'runs/a': 'hash'}, saved)
    with pytest.raises(ValueError, match='differs'):
        reproduce.equal({'runs/a': 'changed'}, saved)


def test_freeze_digest_rejects_tampering(tmp_path):
    path = tmp_path / 'freeze.json'
    value = {'jobs': []}
    value['freeze_sha256'] = reproduce.digest(value)
    path.write_text(json.dumps(value))
    reproduce.verify_freeze(path)
    value['jobs'] = ['extra']
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Freeze changed'):
        reproduce.verify_freeze(path)
