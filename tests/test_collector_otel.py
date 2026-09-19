import json

from vigil.models.event import CanonicalEvent
from vigil.plugins.collector_otel import OTelCollector, _classify_effect

SAMPLE = "examples/otel-export/trace.otlp.json"


def test_collects_all_spans():
    events = OTelCollector().collect(SAMPLE)
    assert len(events) == 5
    assert all(isinstance(e, CanonicalEvent) for e in events)


def test_root_span_opens_the_run():
    events = OTelCollector().collect(SAMPLE)
    assert events[0].kind == "run.start"


def test_gen_ai_attributes_become_canonical_payload_keys():
    events = OTelCollector().collect(SAMPLE)
    llm = next(e for e in events if e.kind == "llm.call")
    assert llm.payload["model"] == "gpt-4o-mini"
    assert "usage" in llm.payload
    tool = next(e for e in events if e.kind == "tool.call")
    assert tool.payload["tool"] == "search_kb"


def test_error_span_carries_message_and_is_flagged():
    events = OTelCollector().collect(SAMPLE)
    failed = [e for e in events if e.payload.get("status") == "error"]
    assert failed, "no span classified as error"
    assert failed[0].payload["error"] == "refund over policy limit"


def test_destructive_tool_is_classified_conservatively():
    events = OTelCollector().collect(SAMPLE)
    refund = next(e for e in events if e.payload.get("tool") == "issue_refund")
    assert refund.effect_class == "destructive"
    search = next(e for e in events if e.payload.get("tool") == "search_kb")
    assert search.effect_class == "read"


def test_unknown_tool_defaults_to_unknown_not_read():
    assert _classify_effect("mystery_call", {}) == "unknown"


def test_declared_effect_class_wins():
    assert _classify_effect("anything", {"vigil.effect_class": "read"}) == "read"


def test_raw_tool_results_are_not_carried_by_default():
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "t1",
                                "spanId": "s2",
                                "parentSpanId": "s1",
                                "name": "get_user",
                                "attributes": [
                                    {
                                        "key": "gen_ai.tool.result",
                                        "value": {"stringValue": "ssn=123-45-6789"},
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    path = "/tmp/vigil-otel-result.json"
    with open(path, "w") as fh:
        json.dump(payload, fh)
    events = OTelCollector().collect(path)
    assert "ssn=123-45-6789" not in json.dumps([e.to_dict() for e in events])


def test_jsonl_span_batches_are_supported():
    with open(SAMPLE) as fh:
        batch = json.load(fh)
    path = "/tmp/vigil-otel.jsonl"
    with open(path, "w") as fh:
        fh.write(json.dumps(batch) + "\n")
    events = OTelCollector().collect(path)
    assert len(events) == 5


def test_collect_is_deterministic():
    a = [e.to_dict() for e in OTelCollector().collect(SAMPLE)]
    b = [e.to_dict() for e in OTelCollector().collect(SAMPLE)]
    assert a == b


def test_token_counts_are_not_treated_as_secrets():
    from vigil.plugins.minimizer_default import DefaultMinimizer

    events = OTelCollector().collect(SAMPLE)
    cleaned, removed = DefaultMinimizer().minimize(events)
    llm = next(e for e in cleaned if e.kind == "llm.call")
    assert "usage" in llm.payload, f"usage dropped: {removed}"
    assert not any("secret_field" in r for r in removed)
