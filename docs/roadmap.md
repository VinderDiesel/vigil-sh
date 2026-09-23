---
translation: roadmap
---

# Roadmap and Decision Gates

Dates are commitments, not wishes. Failing a gate ⇒ **shrink scope or pivot** — never
mask insufficient evidence by adding features.

## G1 — Day 14: collection and minimization that earns trust

| Item | Content |
|---|---|
| Delivers | ✅ three collectors (`file` / `otel` / `langfuse`); PII/secret minimization tests (conformance-covered); lineage (`raw_hash` / `canonical_hash` / `redactions`) |
| Bar | 100% of dangerous fields never appear in artifacts as plaintext in tests; ≥1 external reviewer reproduces collection |
| To verify | external reviewer reproduction (**not done**: needs 1 external user running their own trace) |
| If failed | stop building UI and the signature library; pivot to collector-only |

## G2 — Day 30: Case → Gate end-to-end loop

| Item | Content |
|---|---|
| Delivers | ✅ `CaseManifest`, redacted cases, `docker` environment + `vigil.harness`, deterministic scorers, JUnit/JSON/PR comments |
| Bar | same snapshot passes 10/10 consecutive runs; a planted regression is blocked ≥1/1; no destructive tool ever auto-executes in live mode |
| To verify | 10 repeated runs (needs a working container environment); **external** verification that destructive tools are blocked in live execution |
| If failed | cut the MCP proxy; keep `record-only` |

## G3 — Day 60: external adapters and protocol freeze

| Item | Content |
|---|---|
| Delivers | 3 external teams onboarded; 3 framework/provider combinations; adapter matrix; conformance tests |
| Bar | 3/3 teams complete the import; ≥2/3 reproduce one real failure; manifest diffs parse |
| If failed | protocol converges on v1alpha1; pause cross-framework auto-discovery |

## G4 — Day 90: asset value and statistical validity

| Item | Content |
|---|---|
| Delivers | 10 production (or near-production) failures converted into regressions; judge calibration set; flake triage; repeat-run mechanism |
| Bar | the production-selected case set finds ≥1 real regression more than an equal-size random sample, at ≥1 adopter; false gates are explainable |
| If failed | retire the "reliability platform" narrative; pivot to evaluation-data governance or a governance adapter |

## After that (only if G1–G4 pass)

| Version | Content |
|---|---|
| v0.2 | docker environment, LLM judge + `audit-judge` (meta-eval), statistical gating (requires a declared MDE), flake classifier |
| v1.0 | SLO dashboards, regression diffs, plugin registry, full conformance suite |
| v1.5+ | internal error-signature library (internal first, then cross-org), industry reliability reports |

## Tracked metrics (not stars)

1. **Downstream CI adoption**: independent repositories running `vigil run` in CI.
2. **Plugin owners** (matters more than plugin count).
3. **Production-failure conversion rate**: live failures → rerunnable regressions.
4. **Citations**: papers, vendor docs, RFPs / selection guides.
5. **Explainability**: one sentence per blocking decision.
