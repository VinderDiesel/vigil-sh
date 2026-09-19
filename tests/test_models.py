import pytest

from vigil.models.case import CaseManifest
from vigil.models.gate import FAILURE_TAXONOMY, is_valid_label


def test_manifest_rejects_unknown_spec_version():
    with pytest.raises(ValueError):
        CaseManifest.from_dict({"case_id": "c", "spec_version": "v9"})


def test_manifest_requires_spec_version():
    with pytest.raises(ValueError):
        CaseManifest.from_dict({"case_id": "c"})


def test_determinism_vocabulary():
    assert CaseManifest(case_id="c", replay_mode="snapshot-replay").claims_determinism
    assert not CaseManifest(case_id="c", replay_mode="record-only").claims_determinism
    assert not CaseManifest(case_id="c", replay_mode="live-canary").claims_determinism


def test_taxonomy_is_small_and_usable():
    assert len(FAILURE_TAXONOMY) <= 12
    assert is_valid_label("oracle_ambiguous")
    assert not is_valid_label("vibes")
