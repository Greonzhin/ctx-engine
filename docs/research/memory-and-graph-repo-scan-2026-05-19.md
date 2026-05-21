# Memory And Graph Repo Scan

Date: 2026-05-19

Scope: deep scan of external memory/graph projects requested by user, then map adoptable ideas into ctx-engine roadmap while preserving current safety boundaries.

## Compared Repositories

| Repository | Strong Points | What ctx-engine can adopt | Keep-out decision |
|---|---|---|---|
| `jordanaftermidnight/localmem` | Multi-agent namespaces, hybrid retrieval (dense+sparse+RRF), temporal triples, lifecycle hot/warm/cold, wake-up layers, large MCP tool surface. | Add optional lifecycle tiers to built-in memory, add layered wake profile for capsules, add per-agent namespace option to memory API. | Do not copy broad write-heavy tool surface into P0-style gateway tools. |
| `GuyMannDude/mnemo-cortex` | Session-file watcher ingestion, cross-agent synthesis ("dreaming"), multi-platform setup flow, A2A messaging concepts. | Add optional offline "session ingestion" adapter and scheduled synthesis summary command. | Do not couple ctx-engine to specific external session formats by default. |
| `Arkay92/HoloCortex` | Federated local graphs, signed deltas, trust/provenance-heavy conflict resolution, CRDT-inspired sync. | Borrow contradiction ranking and provenance weighting ideas for memory verify/supersede. | P2 only for federation; no P2P network layer in current local gateway scope. |
| `safishamsi/graphify` | Multimodal graph build, update/watch workflow, explicit inferred-vs-extracted labeling, graph export formats. | Keep explicit confidence tags (`extracted/inferred`) in context artifacts and add watch-mode roadmap note. | No default external vision/model dependency in core ctx-engine path. |
| `tirth8205/code-review-graph` | Incremental graph updates, blast-radius narrowing, broad client auto-install UX, token-efficiency discipline. | Add blast-radius query primitive and retrieval benchmark set for token/context reduction claims. | Keep ctx-engine read-only and avoid auto-modifying user tool configs without explicit command. |
| `ast-grep/ast-grep` | Fast structural pattern search/rewrite via AST with CLI portability. | Add optional structural search adapter for safer symbol/rule extraction. | Do not expose rewrite/codemod operations through ctx-engine tools. |
| `vectorize-io/hindsight` | Mature memory lifecycle/productization, wrapper/SDK paths, benchmark-oriented narrative. | Continue borrowing memory lifecycle semantics and evaluation discipline. | External Hindsight service remains optional P2 adapter, not a P0/P1 dependency. |

## Adoption Roadmap Update

### Near-term (P1.5)

1. Add "memory lifecycle policy" config (hot/warm/cold metadata only, no external service).
2. Add retrieval confidence labels (`extracted`, `inferred`, `ambiguous`) to symbol/docs context.
3. Add blast-radius style query endpoint from local graph edges for review-focused use.
4. Add repeatable retrieval/token benchmark suite with published fixture queries.

### Mid-term (P2)

1. Optional structural-search adapter (`ast-grep`) for higher-precision matching.
2. Optional federated memory experiment branch: signed delta model and trust scoring (HoloCortex-inspired).
3. Optional external memory adapter track (Hindsight/localmem-like) behind strict isolation and explicit opt-in.

## Validation gates before each adoption

- Preserve one local MCP endpoint and read-only default behavior.
- Keep private-code egress guard unchanged.
- Add deterministic tests first, then CLI smoke checks.
- No new always-on background daemons in default install.

## Sources

- https://github.com/jordanaftermidnight/localmem
- https://github.com/GuyMannDude/mnemo-cortex
- https://github.com/Arkay92/HoloCortex
- https://github.com/safishamsi/graphify
- https://github.com/tirth8205/code-review-graph
- https://github.com/ast-grep/ast-grep
- https://github.com/vectorize-io/hindsight
