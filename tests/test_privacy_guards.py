# tests/test_privacy_guards.py
"""Rule #4 enforcement: no GUIDs / person_ids may reach public web/*.json."""
from __future__ import annotations

import re

import pytest

from badminton_tracker.config import ROOT, UPCOMING_JSON

GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
PERSON_ID_RE = re.compile(r'"person_id"')
PUBLIC_FILES = [ROOT / "web" / "data.json", UPCOMING_JSON]


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_public_json_has_no_guid(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    leaked = GUID_RE.findall(text)
    assert not leaked, f"{path.name} leaks profile GUID(s): {leaked[:3]}"


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_public_json_has_no_person_id(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    assert not PERSON_ID_RE.search(text), f"{path.name} leaks a person_id field"
