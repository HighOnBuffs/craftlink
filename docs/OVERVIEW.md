# Architecture overview

Shared core: [craft-libs PR #601](https://github.com/storytold/craft-libs/pull/601). Consumer verification is recorded in [VERIFICATION.md](VERIFICATION.md).

| Owner | Implementation | Responsibility |
| --- | --- | --- |
| Contracts | `craft-link-core::` contracts in the pinned craft-libs dependency | UUIDs, manifests, changes, revisions, native payload origins and capability declarations |
| Durable state | optional native `craft-link-core::Store` in craft-libs | SQLite heads/revisions/history/events, idempotency, DAG validation and SHA-256 snapshot storage |
| Coordination | `crates/broker/src/main.rs` | Authenticated loopback JSON-lines API, blocking replay and saved-file notifications |
| Native projections | `crates/broker/src/native.rs` | VectorCraft/FigCraft command clients, placement, applied baselines, conflict snapshots and reconnect |
| External integration | `sdk/`, `manifests/`, `examples/` | Python client, MCP facade, manifest schema and generated-app reference |
| Optional launcher view | [launcher PR #1239](https://github.com/storytold/craft-launcher/pull/1239) | Read-only binding status in existing app details; explicit connection, transient credentials, feature off by default |
| Atomic blob writes | shared `craft-atomic` dependency | Pinned upstream staging/fsync/replace primitives; preserved licenses and provenance |

## Commit and update flow

An adapter stages an immutable native snapshot and submits semantic changes with expected revisions and a unique operation ID. One SQLite transaction commits heads, history, dependency invalidation, an event and an idempotency receipt. Saved-file notifications or SDK calls then reconcile each native application against its recorded baseline. Consumers replay committed events from a sequence cursor.

The broker's durable commit and each application's UI/save completion are separate. If an app disconnects, its binding retains the applied revision. A local value differing from both baseline and incoming value becomes a conflict with retained native snapshots. Undo/redo create new monotonic revisions. Reverse semantic edits target the same canonical object rather than adding a cyclic dependency edge.

## Boundaries to preserve

Applications own native models, serializers, renderers and standalone editing. Only rectangle name/opacity synchronize today; placement initializes axis-aligned bounds. Opaque snapshots preserve source data without promising its editability in another app.

The broker authenticates a trusted-project credential and confines native paths. Stock app ports retain their documented authentication/conditional-write limitations. A separate native worker keeps slow application I/O outside the metadata lock. Candidate FigCraft routes by live document ID; candidate VectorCraft guards the active bound document. Both authenticated candidates support conditional writes and unsaved command invalidations. Guarded snapshot capture and pending-receipt recovery are verified in [the live slice](VECTOR_LIVE.md). Other mutation paths, richer semantic contracts and launcher discovery/asset browsing remain open. There is no distributed ACID guarantee across native files, no required cloud and no installed-app modification in this repository.
