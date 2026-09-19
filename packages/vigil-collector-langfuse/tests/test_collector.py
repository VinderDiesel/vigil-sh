import json
import subprocess
import sys
from pathlib import Path

import pytest
from vigil.models.event import CanonicalEvent

from vigil_collector_langfuse import LangfuseCollector

# resolve relative to this file so the suite works from the repo root too
EXPORT = str(Path(__file__).resolve().parent.parent / "examples" / "export.json")


def test_collects_every_observation():
    events = LangfuseCollector().collect(EXPORT)
    assert len(events) == 4
    assert all(isinstance(e, CanonicalEvent) for e in events)


def test_shared_trace_becomes_one_run():
    events = LangfuseCollector().collect(EXPORT)
    assert {e.run_id for e in events} == {"trace-abc"}


def test_generation_maps_to_llm_call():
    events = LangfuseCollector().collect(EXPORT)
    llm = next(e for e in events if e.kind == "llm.call")
    assert llm.payload["model"] == "gpt-4o-mini"
    assert llm.payload["usage"]["promptTokens"] == 128


def test_error_level_becomes_error_event():
    events = LangfuseCollector().collect(EXPORT)
    failed = [e for e in events if e.kind == "error"]
    assert failed
    assert failed[0].payload["error"] == "refund over policy limit"


def test_destructive_tool_classification():
    events = LangfuseCollector().collect(EXPORT)
    refund = next(e for e in events if e.payload.get("tool") == "issue_refund")
    assert refund.effect_class == "destructive"


def test_io_is_digest_only_by_default():
    events = LangfuseCollector().collect(EXPORT)
    blob = json.dumps([e.to_dict() for e in events])
    assert "Refunds are allowed within 14 days" not in blob
    assert any(e.payload.get("completion_digest") for e in events)


def test_include_io_carries_raw_text():
    events = LangfuseCollector().collect(EXPORT, include_io=True)
    llm = next(e for e in events if e.kind == "llm.call")
    assert "14 days" in llm.payload["output"]


def test_deterministic():
    a = [e.to_dict() for e in LangfuseCollector().collect(EXPORT)]
    b = [e.to_dict() for e in LangfuseCollector().collect(EXPORT)]
    assert a == b


def test_limit_option():
    events = LangfuseCollector().collect(EXPORT, limit=2)
    assert len(events) == 2


def test_api_mode_requires_credentials(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="public_key"):
        LangfuseCollector().collect("langfuse://cloud.langfuse.com")


def test_api_mode_uses_stubbed_transport(monkeypatch):
    captured = {}

    def fake_fetch(self, url, public_key, secret_key, params):
        captured.update(url=url, params=params, public_key=public_key)
        return {"data": [{"id": "o1", "traceId": "t1", "type": "GENERATION", "name": "chat"}]}

    monkeypatch.setattr(LangfuseCollector, "_fetch_json", fake_fetch)
    events = LangfuseCollector().collect(
        "langfuse://cloud.langfuse.com",
        public_key="pk",
        secret_key="sk",
        since="2026-09-01",
    )
    assert captured["url"] == "cloud.langfuse.com/api/public/observations"
    assert captured["params"]["fromStartTime"] == "2026-09-01"
    assert len(events) == 1
    assert events[0].kind == "llm.call"


def test_httpx_is_not_imported_at_module_level():
    code = "import importlib, sys;import vigil_collector_langfuse;print('httpx' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.stdout.strip() == "False", result.stderr


def test_conformance_contract():
    from vigil.conformance import assert_collector_contract

    assert_collector_contract(LangfuseCollector, EXPORT)
