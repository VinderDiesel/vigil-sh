---
translation: handbook
---

# Agent Reliability Handbook (draft)

> Intended readers: teams wiring agents into production. This is methodology, not
> product documentation. Draft at v0.1 — corrections via issues are welcome.

## 1. Why "success rate" is not enough

Agent behavior is stochastic: model versions, retrieval corpora, tool schemas and
external APIs all drift. A single 0/1 score breaks down on every one of these:

- the same case run three times: two passes, one failure
- pass_rate moved 0.92 → 0.915 — regression or noise?
- mean latency looks fine while P95 tripled
- success rate climbs while the human-intervention rate climbs too (the agent learned
  "when lost, escalate to a human")

**You are signing an SLA, not a score.** Track at minimum:

| Metric | Why |
|---|---|
| `pass@k` | success over k attempts is closer to real experience than a single run |
| `p95_latency` | users feel the tail, not the mean |
| `p95_cost` | cost blowouts live in the long tail |
| `intervention_rate` | rising human intervention often masquerades as "rising success rate" |
| `unrecoverable_rate` | errors retries cannot fix are the true enemy of the SLA |
| `flake_rate` | share of cases whose verdict changes across repeats |
| long-horizon decay | how much success drops per N extra steps (long tasks are agents' soft spot) |

## 2. Five layers of "replay" and their honest boundaries

Do not ask "can it be replayed"; ask "replayed down to which layer".

| Layer | Pinnable? | Typical means |
|---|:--:|---|
| model + sampling params | ✅ | pin version + temperature + seed |
| input and initial state | ✅ | snapshot |
| tool protocols and responses | ✅ (if the protocol can be pinned) | MCP proxy record/replay |
| external world, time, randomness | ⚠️ partially | clock freezing, mocks, allowlists |
| the oracle itself | ⚠️ easily forgotten | oracle versioning + human review |

For irreversible side effects (payments, deletions, sent mail, revoked permissions),
**do not chase replay**; chase "dry-run by default + explicit authorization + full audit".

## 3. From production traces to regression cases

1. **Select**: failures, human takeovers, irreversible side effects, cost/step
   threshold breaches, collection gaps.
2. **Minimize**: PII masking, secret redaction, field allowlists, keep a record.
3. **Deduplicate carefully**: dedupe only at the canonical-hash layer; semantic
   clustering results are **advisory for human review only** — never auto-delete.
4. **Human-confirmed oracles**: an auto-generated oracle freezes today's mistake as
   tomorrow's standard.
5. **Version and expire**: bump the oracle version when it changes; give cases an `expires_at`.
6. **Into CI**: JUnit/SARIF, so failures show up in pull requests, not quarterly retros.

## 4. A judge is not an oracle

- Prefer a deterministic scorer whenever one exists.
- Every judge must declare its version; LLM judges must also record a prompt digest so drift is detectable.
- Allow abstention; record disagreement; cases with large spread go to the human queue automatically.
- Run meta-eval periodically: agreement with human labels, self-consistency, cross-version drift, length/format bias.
- **The labeling set must be independent of routine production data**, otherwise you are validating a model against itself in a loop.

## 5. The two gate errors

| | blocking (false gate) | passing a regression (missed) |
|---|---|---|
| Cost | work interrupted; the team starts ignoring the gate | problems reach production |
| Control | declared minimum detectable effect, repeats, flake triage | hard safety thresholds, baseline comparison |

**Hard gates (safety / PII / policy / irreversible side effects) are never waived**;
soft thresholds should warn, not block, until an MDE has been declared.

## 6. False alarms are the biggest enemy

`oracle_ambiguous` must be a first-class category. Track the share of "the case itself
was wrong" — once it exceeds 5%, trust in the evaluation system collapses quickly, and
every gate after that gets bypassed.

## 7. Suggested rollout order

1. Turn one real production failure into a rerunnable case (even by hand).
2. Wire it into CI with hard gates only.
3. Measure flakes; run everything three times.
4. Add deterministic scorers before talking about LLM judges.
5. After 50 human-labeled examples, talk about meta-eval and automatic attribution.
6. After a stable internal signature library, talk about cross-org sharing.
