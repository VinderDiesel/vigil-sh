---
translation: architecture
---

# Architecture

## 1. Positioning: the control plane for reliability assets

Vigil does not fight for the infrastructure layer (OTel collectors, trace stores,
sandboxes) or the integration layer (framework SDKs, CI). It occupies the **asset
layer**: cases, contracts, manifests, scores, SLOs, signatures and gate decisions.

```
┌─────────────── Integration layer (others build it) ──────────────┐
│ Framework SDKs · MCP · CI · observability-platform exports       │
└────────────────────────────┬─────────────────────────────────────┘
                             ▼
┌─────────────── Asset layer (Vigil) ──────────────────────────────┐
│ CanonicalEvent → CaseManifest → Score → Gate                     │
└────────────────────────────┬─────────────────────────────────────┘
                             ▼
┌─────────────── Infrastructure layer (others build it) ───────────┐
│ Object storage · containers · K8s · Proxmox · snapshot backends   │
└───────────────────────────────────────────────────────────────────┘
```

The payoff of this split: we do not replicate Langfuse/Phoenix storage and UI, do not
replicate Inspect/Orchard environment implementations, and never collide head-on with
Microsoft AGT in the governance-enforcement layer.

## 2. Core chain and modules

| Stage | Module | Output |
|---|---|---|
| collect | `plugins/collector_file` / `collector_otel` / external package `langfuse` | `CanonicalEvent[]` |
| minimize | `plugins/minimizer_default.py` | redacted events + `redactions` |
| select | `plugins/selector_rules.py` | candidate runs (with trigger signals) |
| mint | `models/case.py` + `cli.mint` | `CaseManifest` |
| run | `runner.py` + `envbase` + `plugins/env_noop` / external package `docker` | `RunResult` |
| score | `plugins/scorer_*` → `models/result.py` | `JudgeVerdict[]` |
| aggregate | `runner.aggregate` | `Aggregate` |
| gate | `plugins/gate_hard.py` → `models/gate.py` | `GateDecision` |
| report | `artifacts.py` | JUnit / JSON / PR comment |

## 3. Key design decisions and why

| Decision | Rationale |
|---|---|
| Zero third-party dependencies in core | `pip install` and it runs; distribution cost decides early survival |
| CLI built on stdlib argparse | same reason; heavyweight CLI frameworks belong plugin-side |
| Plugins discovered via entry points; built-ins get no privileged path | a rotting built-in is a worse role model than any third-party plugin |
| `spec_version` strictly validated | silent schema drift is the hardest bug class to trace |
| Three hash layers kept separate | deduplicating on semantic clusters deletes the rarest failures |
| Judges may abstain; disagreement is surfaced | LLM-as-Judge drift is the public enemy No. 1 |
| Environment unverified ⇒ `UNDETERMINED` | an unverified PASS is far more harmful than a FAIL |
| Hard gates separated from soft thresholds | statistically waiving safety thresholds means having no thresholds |
| `UNDETERMINED` maps to skipped in JUnit | "silence" is where flakes hide |
| No statistical gating in v1alpha1 | a half-built gate trains teams to rerun CI until it goes green |

## 3.1 Core vs external packages

| Capability | Lives in | External dependency |
|---|---|---|
| `file` / `otel` collectors, minimization, selection, `noop` env, deterministic scorers, hard gate | **core** | none (stdlib only) |
| `langfuse` collector | `packages/vigil-collector-langfuse` | httpx (optional, imported inside functions, API mode only) |
| `docker` environment | `packages/vigil-env-docker` | Docker daemon (shell-outs to the CLI) |

One test decides placement: **core must run after plain `pip install vigil-sh`**.
Any SDK or daemon requirement goes into an external package.

## 3.2 Environment capability contract

Environments declare `capabilities`; `vigil.envbase.enforce` is the single arbiter.
A request beyond declared capabilities raises `CapabilityError` → the runner degrades
to `UNDETERMINED`. `clock_policy=frozen` is the only advisory capability (absence
warns, never blocks). See `spec/v1alpha1/environment.md` and RFC 0003.

## 3.3 Cross-boundary execution

In-process environments call the callable directly; container/remote environments go
through `vigil.harness`:

```
case.json + agent.py (mounted read-only) → python -m vigil.harness → RunResult JSON (stdout)
```

## 4. Dependency direction

`collector → minimizer → selector → environment → scorer → gate`, one way only.
Plugins may depend on `vigil.models.*` and `vigil.cas`; plugins must never import each
other's implementations; cross-layer needs travel through the manifest.

## 5. Fail-first design

Every stage defaults to "undetermined", not to "passed":

- collection gap → `observed=false` → classified `unobserved_side_effect`
- missing oracle → scorer abstains → `UNDETERMINED`
- scorer crashes → abstention + warning, the suite continues
- environment restore fails → `UNDETERMINED`, never a PASS
- execution raises → `ERROR`, no verdict can paper over it

## 6. Evolution path

See the decision gates (G1–G4) in the README. Architectural headroom already reserved:

- `EnvironmentProvider` defines `provision/restore/teardown`; the v0.2 docker environment only implements this SPI.
- `Scorer` returns `JudgeVerdict`; v0.2's LLM judge and `audit-judge` (meta-eval) need no protocol change.
- `Gate.decide(aggregate, slos)` already takes an SLO list; v0.2 statistical gating can be a new plugin without touching the signature.
