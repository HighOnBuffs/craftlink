# Adapter SDK v1

## Contracts and registration

Rust contracts live in the pinned `craft-link-core` dependency proposed in craft-libs PR #601. Native storage is optional; disabling its native feature leaves pure contracts. The pure contract has passed an actual wasm32 compilation.

Upstream extraction update: `craft-link-core` is proposed in craft-libs PR #601,
pinned consumer revision `46d38608042c17ebaf5aaa9bf82bc0df61fde68f`. Its pure
contracts have now passed an actual `wasm32-unknown-unknown` build. No non-Windows application runtime is claimed.

The application manifest is the serialized Rust `Manifest`. See `manifests/*.json` and `sdk/manifest.schema.json`. `schema: 1` is required. Unknown manifest fields fail closed. `object_types` maps arbitrary semantic type names to permitted writable property names; `read`, `write`, `representations`, `fidelity`, `history` and `transactions` disclose the actual adapter boundary. `lifecycle`, `authentication` and `filesystem` describe the adapter's connection and permission policy. These description strings do not grant OS permissions or execute endpoints. The current broker supports externally launched applications only. Adding a custom semantic application/type requires registration, not a Core code change.

IDs are UUID strings. Document identity is independent of path; source, placement, link and operation identities are separate. Binary asset identity is SHA-256; `NativePayload` contains `hash`, `format` and originating `application`. A reverse edit can carry the receiver's native format, so never infer its format from the canonical object's owner. The original source file and its snapshots are preserved independently.

## Authenticated local protocol

One JSON line per TCP connection to `127.0.0.1`; one response then close. Requests: `{"token":"<private project credential>","method":"...","params":{...}}`. Replies: `{"ok":true,"result":...}` or `{"ok":false,"code":"conflict|capability|missing|invalid|storage|authentication","error":"..."}`. Requests are bounded to 1 MiB, incoming read inactivity to 10 seconds, subscriptions to 30 seconds, concurrent sockets to 16. The SDK bounds replies to 8 MiB. Native files are not transported through the broker protocol. A conflict snapshot may use the native app's copy API once.

The project token is a single trusted-project capability: holders can register adapters and write that project's semantic store. It is not per-application isolation. Keep it in a private inherited channel/environment, keep project files protected by OS permissions, and do not publish it in manifests, command lines or logs. Native bindings require existing canonicalized native files under the explicit project root, outside `.craftlink`; symlinks are resolved. No arbitrary filesystem API or executable-launch endpoint is exposed. The source app's root flags provide additional enforcement. Its unmodified control protocol is still an upstream authentication limitation.

| Operation | Parameters / behavior |
| --- | --- |
| `register_application` | Full manifest; register or replace identity under trusted project credential |
| `negotiate_capabilities` | `{application,kind,properties:[...],write}`; explicit unsupported-property error |
| `enumerate_objects`, `search_assets` | Optional `{query}`; inspect committed semantic objects |
| `begin_transaction` | Returns a fresh operation ID; staging is client-side |
| `apply_changes`, `commit_transaction` | `{operation,changes:[{object,document,application,kind,expected,value,native}]}`; same atomic commit path |
| `rollback_transaction` | Discard client-side staging; never reverses a committed operation |
| `resolve_link` | `{object}`; current immutable head record |
| `create_link` | `{id,source,target,mode}`; mode `semantic`, `source`, `preview`; DAG edge between existing objects |
| `dependencies` | Upstream/dependent object pairs; canonical semantic edits flow back to the same object, not a cyclic reverse edge |
| `subscribe_to_changes` | `{after,timeout_ms}`; blocking committed event replay, at most 256 rows; repeat from last sequence |
| `undo`, `redo` | `{operation,object,expected}`; new monotonic revisions, optimistic guard, retryable receipt |
| `conflicts` | Rejected intents / full native snapshot references |
| `bind_native` | Existing source rectangle `{id,object,profile,port,path,node,baseline:{name,opacity},applied}` |
| `place_link` | `{id,source_binding,profile,port,path,document,placement,link,operation}`; actual native creation and dependency edge; path is an existing saved target document |
| `bindings` | Persistent applied revision, baseline, current/stale/applying/locally-modified/conflicted/missing/frozen status and fidelity disclosure |
| `native_changed` | `{binding}`; explicit saved-change notification when the app can emit it directly |
| `reconnect` | `{binding,port?,path?,node?}`; same identity, new endpoint or recovered path |
| `open_in_source_application` | `{binding}`; select bound native object in an already connected source session; external launcher lifecycle is pending |
| `freeze`, `detach` | `{binding}`; stop updates, keep the native object and retained history |
| `resolve_conflict` | `{binding,choice:"committed"}`; explicit overwrite of supported properties after preserving conflicting native snapshot; local intent can instead be submitted as a new guarded transaction |

For native rectangles, value is exactly `{name: string, opacity: number from 0 to 1}`; the two profiles convert their native opacity units. Unsupported edits fail explicitly before a bound canonical commit. Inspect `bindings` after commits: a durable commit can succeed while one app is missing or conflicted. Native UI writes are not distributed transactions.

### Optional live native profile

`bind_native` and `reconnect` accept `live: true` and `token_file` for a compatible
candidate FigCraft or VectorCraft. Live mode fails closed without a credential file inside the
explicit project root and runtime `conditionalExecute: 1` / `documentChangeEvents: 1`
capabilities. Authentication uses the first-request `auth` protocol proposed by
FigCraft #1473 / VectorCraft #4623. Native credential contents are never returned or logged.

The adapter subscribes to the existing `events.poll` document topic, coalesces
invalidation, and inspects current semantic properties. It retains immutable full
native bytes for an actual unsaved semantic revision. Snapshot export is guarded
at the observed revision; extra revision movement rejects A→B→A capture. FigCraft's
verified byte-copy bookkeeping advances its revision once, which the adapter
accounts for explicitly. Property writes carry `{expected: {document, revision}}`.
FigCraft routes by live document ID. The updated VectorCraft candidate routes
guarded name/opacity writes and native snapshots to background document UIDs,
preserving the foreground tab and tool; unsupported background commands fail
explicitly. Older candidates remain active-document-only. A completed pending projection survives
broker interruption without becoming a new local edit; explicit reconnect also
retires the old subscription when a native process reuses its port/ID.
Native ids/revisions are process-local, distinct from CraftLink UUIDs. Reconnect
refreshes them. Live projection keeps the receiver unsaved; saving stays an explicit
native action. Use VectorCraft `app.save {wait:true}` before closing: native
background-save acknowledgement precedes completed file IO. Stock apps keep their
previous saved-file adapter behavior. Exact candidate pins/reproduction: [VECTOR_LIVE.md](VECTOR_LIVE.md).

Committed metadata responses no longer wait for native projection. Native work
runs on a separate bounded worker queue/SQLite connection, so a stalled editor does
not hold the metadata lock. Queue overflow retains a recovery flag and triggers a
current-state rescan; this is event-driven, not periodic polling. Native jobs are
currently serialized with each other; unrelated editors may still wait for a slow
projection even though metadata remains available.

## Revisions, history and recovery

Every commit needs a unique `operation` and each changed object's observed `expected` revision (zero for creation). Retry the **exact** request with the same operation ID after a lost reply. Reusing an ID for different contents conflicts. Multiple objects commit together; one stale expected revision rolls back all updates and retains the rejected intent. No-op changes do not create revision/event churn. Undo/redo operate on CraftLink semantic history; they do not rewind unrelated native GUI history.

Stage/fsync immutable blobs through `Store::put_blob` before committing a reference. SQLite WAL/FULL is the commit point for heads, revision records, history stacks, invalidation, event and idempotency receipt. The public broker currently accepts only references already in its store; an authenticated streaming blob-upload SDK is not implemented. Native adapters publish snapshots through the in-process storage API.

After restart, replay from the last durable event sequence and resolve the latest head; persist the applied head and native baseline only after verifying the native edit and save. The native adapter writes `pending` before side effects. A discovered local value different from both baseline and desired is retained as a conflict; disconnected saved edits are ingested at broker startup. A marker-based native creation intent makes lost placement replies recoverable without blind duplication. Placement intent, placement-object creation, edge creation and binding publication are separately durable steps of a resumable workflow, not a multi-file atomic commit. Automatic recovery of every placement interruption point still needs fault-injection acceptance.

Subscriptions are at-least-once replay; consumers deduplicate by sequence/operation. Do not send blobs with each event. No cloud or periodic scan is needed. Notifications use native filesystem events, debounced after activity; offline recovery inspects persisted bindings. The event log is currently unbounded and has no retention/migration policy beyond initial schema 0 → 1 and rejection of newer schemas.

## Future application and agents

`examples/generated_app.py` is a runnable registration/commit/resolve reference for a generated notes app. It is a separate process and defines a new semantic type without modifying Core. Extend it with native UI/model projection and durable cursors in the application's own engine. It is not evidence of a third production native adapter.

`sdk/mcp_server.py` exposes the documented operations as a stdio MCP tool. Its actual initialize, tools/list and tools/call flow is tested with a subprocess. No tool sends messages or publishes assets. Full application discovery and native launcher/asset-browser UI are later work; use the launcher's existing catalog/detection/lifecycle owners rather than adding another installer.
