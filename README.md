<p align="center">English &nbsp;|&nbsp; <a href="README_zh.md"><b>简体中文</b></a></p>

# Vigil

**Turn one agent execution into a replayable, scoreable, gateable reliability asset.**

Vigil is not a tracing platform, not a benchmark leaderboard, and not yet another LLM
evaluation framework. It is the layer that connects production evidence to engineering
gates: it consumes exports from existing observability platforms, produces versioned
regression cases, replays them in controlled environments, judges them with multiple
scorers, and finally emits an actionable allow/block decision for CI.

> **Status**: v0.1.0-alpha, spec version `v1alpha1`. The protocol is not frozen —
> do not use it for critical production decisions yet.
> **License**: MIT.

---

## 1. What we deliberately do NOT do

These boundaries matter more than any feature list. Cross one of them once and the
project falls into a battlefield that already has strong incumbents.

| Not doing | Why | Use instead |
|---|---|---|
| Tracing / observability UI | Langfuse, LangSmith, Phoenix already do this well | They are Vigil's **input sources** |
| A self-hosted benchmark leaderboard | Expensive and undifferentiated | SWE-bench, τ²-bench, OSWorld, GAIA |
| A general-purpose eval runner | Inspect, DeepEval, Promptfoo cover it | Reuse them as scorers / execution backends |
| Agent runtime governance | Microsoft AGT intercepts and audits from the app layer | Interoperate, never replace |
| LLM-as-Judge as the sole referee | Judges drift; they must be calibrated | Deterministic scorers first |
| **"Any execution can be deterministically replayed"** | **We can't do it, so we don't claim it** | See the five replay modes below |

**Vigil's differentiation is not any single capability — it is the asset chain**:
`execution → canonical event → case contract → score → gate artifact`.
No open, portable, auditable implementation of this chain exists today.

---

## 2. The core chain

```
  Execution          CanonicalEvent         CaseManifest          Score            GateArtifact
 (any source)  →   (canonicalized +     →  (versioned      →   (scored +     →   (JUnit/JSON)
                    redacted)                 contract)          abstention)
       ▲                                        │
       └────────────  replay ────────────────────┘
```

| Stage | Output | Hard constraint |
|---|---|---|
| collect | `CanonicalEvent[]` | Three hash layers — `raw_hash` / `canonical_hash` / `cluster_id` — are never mixed |
| minimize | redacted events | **Default deny**: unknown fields are dropped; PII inside known fields is masked |
| select | candidate runs | Rule-driven, reproducible; v1alpha1 does **not** do semantic dedup (it deletes the rarest failures) |
| mint | `CaseManifest` | Oracles must be human-supplied; unreviewed cases carry `confidence=0.3` |
| run | `RunResult` + artifacts | Environment not verified ⇒ result forced to `UNDETERMINED` |
| gate | `GateDecision` | Hard SLOs are never waived; statistical gating is not in v1alpha1 |

---

## 3. Five replay modes (where the promises stop)

"Replayable" is tiered. Every case must **explicitly declare** which tier it belongs
to, and the CLI prints the vocabulary it is allowed to use.

| Mode | Fits | May we say "replay"? |
|---|---|---|
| `record-only` | audit only, never rerun | ❌ say "recorded" only |
| `mock-replay` | tool responses replayed from recording | ✅ |
| `snapshot-replay` | fs/db/container state restored from snapshot | ✅ (within the snapshot boundary) |
| `sandbox-execute` | real execution inside a controlled env | ✅ |
| `live-canary` | external state keeps moving | ❌ say "contract check" only |

Irreversible side effects — real money, deletions, sending email, revoking permissions —
default to `dry-run`. Live execution requires the environment plugin to declare the
capability; a case YAML can never grant itself that privilege.

---

## 4. Quickstart (~5 minutes; no Docker, no cloud, no model keys)

```bash
pip install vigil-sh           # release (the PyPI name `vigil` was taken, hence `vigil-sh`)
pip install -e ".[dev]"        # from source (development in this repo)

# 1) see installed plugins
vigil plugins

# 2) collect + minimize one trace (JSONL / OTLP / Langfuse export → canonical events)
vigil collect examples/minimal-agent/trace.jsonl --out collected.json
vigil collect examples/otel-export/trace.otlp.json --collector otel --out otel.json

# 3) pick which runs deserve to become cases
vigil select examples/minimal-agent/trace.jsonl --options '{"signals":["failure","destructive"]}'

# 4) mint a case (oracle is mandatory; auto-generating oracles is out of scope)
vigil mint --case-id case:demo --input '{"question":"refund-policy"}' \
           --oracle '{"contains":["14 days"]}' --out cases/demo.json

# 5) run the suite, emit JUnit + JSON + PR comment; the exit code IS the gate
vigil run --cases examples/minimal-agent/cases \
          --agent examples/minimal-agent/agent.py \
          --junit vigil-junit.xml --json vigil-report.json --comment pr-comment.md
echo $?   # 0 = allow, 1 = block
```

Your agent only has to expose one function:

```python
def run(case: CaseManifest) -> RunResult: ...
```

Pass a **file path** to `--agent` and Vigil wraps it as a `LoadedAgent`: in-process
environments call it directly; container/remote environments mount the file into the
sandbox and execute it via `python -m vigil.harness` (a live callable cannot cross a
process boundary).

---

## 5. CI integration example

```yaml
- name: vigil reliability gate
  run: |
    vigil run --cases cases/ \
              --agent tests/agent_harness.py \
              --env docker \
              --scorer exact,llm \
              --repeats 3 \
              --slo vigil-slo.json \
              --junit vigil-junit.xml --json vigil-report.json --comment pr.md
- name: publish report
  if: always()
  uses: actions/upload-artifact@v4
  with: { name: vigil-report, path: vigil-junit.xml }
```

Default SLOs (when `--slo` is not given):

| metric | threshold | class |
|---|---|---|
| `policy_violations` | max 0 | **hard** |
| `unrecoverable_rate` | max 0.05 | **hard** |
| `pass_rate` | min 0.90 | soft (warn only) |
| `p95_cost_usd` | max 0.25 | soft |
| `flake_rate` | max 0.02 | soft |

Soft thresholds do **not** block the build in v1alpha1. Reason: statistical gating
without a declared minimum detectable effect trains teams to rerun CI until it goes
green — which is worse than having no gate at all.

---

## 6. Failure taxonomy (v1alpha1, 8 classes only)

`tool_argument` · `tool_permission` · `state_transition` · `policy` · `oracle_ambiguous` ·
`environment_flake` · `model_reasoning` · `unobserved_side_effect`

`oracle_ambiguous` (**the case itself is wrong**) is a first-class citizen. The most common
failure of an evaluation system is misjudging the case, not misjudging the agent. Every
case carries `confidence` and `expires_at`; expired cases cannot participate in gating.

---

## 7. Plugin system

Six plugin categories, all registered via `importlib.metadata` entry points — built-ins
take the **exact same** path as third-party plugins:

| Group | Responsibility | Built in v0.1 |
|---|---|---|
| `vigil.collectors` | vendor trace → canonical events | `file` (reference), `otel` (core); `langfuse` (separate package) |
| `vigil.minimizers` | redaction / minimization | `default` |
| `vigil.selectors` | pick candidate runs | `rules` |
| `vigil.environments` | stand the world up, tear it down | `noop` (core, in-process only); `docker` (separate package) |
| `vigil.scorers` | one opinion per run, may abstain | `exact`, `contains` |
| `vigil.gates` | allow / warn / block | `hard` |

See [`packages/`](packages/): anything needing httpx / the Docker daemon stays out of
core, and heavy dependencies are imported lazily inside functions. Environment plugins
must declare `capabilities`; `vigil.envbase.enforce` refuses out-of-contract requests —
**a case YAML cannot privilege itself**.

Dependency direction is one-way only:
`collector → minimizer → selector → environment → scorer → gate`.
Cross-layer needs go through the manifest; plugins never import each other's implementations.

Maintenance tiers: `core` (project-maintained, semver guaranteed) / `maintained` (named
owner) / `community` (no guarantee, clearly labeled in its README).

Writing a plugin: implement the matching Protocol (`vigil/protocol.py`), declare an entry
point in `pyproject.toml`, then run `pytest conformance/` — **a plugin that fails
conformance cannot be listed in the registry**.

---

## 8. Roadmap and decision gates

Dates are commitments, not wishes. If a gate fails, we shrink scope or pivot —
we never mask missing evidence by adding features.

| Gate | Day | Delivers | Passing bar |
|---|---|---|---|
| **G1** | 14 | collect + minimize + lineage (`file`, `otel`, `langfuse` collectors) | 100% of dangerous fields absent from raw artifacts; ≥1 external reviewer reproduces it |
| **G2** | 30 | `collect → mint → run → gate` closed loop (incl. `docker` env, `vigil.harness` sandbox probe) | same snapshot 10/10 pass; a planted regression blocked 1/1 |
| **G3** | 60 | 3 external teams onboarded + protocol frozen | 3/3 complete import, ≥2/3 reproduce one real failure |
| **G4** | 90 | production-failure conversion + judge calibration | the production-selected case set finds ≥1 real regression more than random sampling |

Only after that: `v0.2` (statistical gating, docker env, LLM judge + meta-eval),
`v1.0` (SLO dashboards, flake triage, conformance suite).

**Out of scope for the first round**: generic MCP record/replay, a cross-org public error
signature library, semantic dedup, self-built model providers, full dashboards, generic
MCP fuzzing, leaderboards, automatic oracle generation.

---

## 9. Success metrics (not stars)

1. **Downstream CI adoption**: independent repositories running `vigil run` in CI (the only metric hard to game).
2. **Number of plugin owners** (matters more than plugin count — is the ecosystem single-points-of-failure?).
3. **Production-failure conversion rate**: share of live failures that become rerunnable regressions.
4. **Citations**: papers, vendor docs, RFPs / selection guides.
5. **Explainability**: can every blocking decision be stated in one sentence?

---

## 10. Privacy and compliance red lines

- Core has **zero third-party dependencies** and performs no network I/O; all external contact happens inside plugins.
- Minimization is default-deny: unknown fields dropped, PII in known fields masked, **every removal recorded**.
- Real secrets never enter cases; CI uses least-scope tokens.
- Error fingerprints report local hashes only, never raw traces (v1alpha1 enables no telemetry at all).

---

## 11. Contributing

Read [AGENTS.md](AGENTS.md) first (the engineering protocol for AI coding tools and
contributors) and [CONTRIBUTING.md](CONTRIBUTING.md).

- Protocol changes → open an RFC (`RFC/0000-rfc-template.md`)
- New plugin category → RFC + conformance, always
- Security vulnerabilities → see [SECURITY.md](SECURITY.md), please do not open a public issue

## License

MIT, see [LICENSE](LICENSE).
