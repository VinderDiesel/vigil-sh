---
translation: home
---

# Vigil

**Turn one agent execution into a replayable, scoreable, gateable reliability asset.**

Vigil is not a tracing platform, not a benchmark leaderboard, and not yet another LLM
evaluation framework. It is the layer that connects production evidence to engineering
gates: it consumes exports from existing observability platforms, produces versioned
regression cases, replays them in controlled environments, judges them with multiple
scorers, and finally emits an actionable allow/block decision for CI.

!!! warning "Status"
    v0.1.0-alpha, spec version `v1alpha1`. The protocol is not frozen — do not use it
    for critical production decisions yet.

## The core chain

```
  Execution          CanonicalEvent         CaseManifest          Score            GateArtifact
 (any source)  →   (canonicalized +     →  (versioned      →   (scored +     →   (JUnit/JSON)
                    redacted)                 contract)          abstention)
       ▲                                        │
       └────────────  replay ────────────────────┘
```

## Documentation

- [Architecture](architecture.md) — layering, dependency direction, and the reasoning behind the plugin design
- [Reliability handbook](reliability-handbook.md) — methodology: abstention, disagreement, replay modes and vocabulary discipline
- [Roadmap](roadmap.md) — decision gates G1–G4 and scope-shrink conditions

The engineering protocol (for contributors and coding agents) lives in
[AGENTS.md](https://github.com/VinderDiesel/vigil-sh/blob/main/AGENTS.md); the normative
text lives in [spec/v1alpha1](https://github.com/VinderDiesel/vigil-sh/tree/main/spec/v1alpha1).

## Quickstart

```bash
pip install vigil-sh           # the distribution
vigil plugins                  # list registered plugins
```

The end-to-end demo (collect → mint → run → gate, ~5 minutes, no Docker / cloud /
model keys needed) lives in
[`examples/minimal-agent/`](https://github.com/VinderDiesel/vigil-sh/tree/main/examples/minimal-agent).
