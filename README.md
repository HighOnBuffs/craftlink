# CraftLink

Experimental local interoperability for the Craft App Suite. Native applications retain their document models and editing engines; CraftLink coordinates committed semantic revisions and recoverable projections.

Shared core proposal: [storytold/craft-libs#601](https://github.com/storytold/craft-libs/pull/601), discussion [#600](https://github.com/storytold/craft-libs/issues/600). This consumer repository pins that proposed core commit; it is not merged upstream or an official release.

## Implemented boundary

- Authenticated loopback broker, durable revisions/events, immutable native snapshots, dependency inspection, optimistic conflicts and managed undo/redo.
- Native VectorCraft 0.21.0 ↔ FigCraft 0.15.0 rectangles: name/opacity synchronization on save and editable placement from axis-aligned bounds. Paints, paths, rotation, typography and effects are not transferred.
- Optional candidate FigCraft integration for unsaved command notifications and conditional writes, with explicit capability checks and the upstream control-token protocol. Stock installed apps keep the saved-file path.
- Capability manifests, Python SDK, generated-app registration example and stdio MCP facade. Native I/O runs outside the metadata lock; committed heads remain readable while projection waits.

Broker metadata commits and native UI updates are separate. Native documents and opaque snapshots are retained; this is not universal lossless interchange. Only the optional candidate native endpoint has conditional writes; the legacy VectorCraft endpoint retains its documented inspect/apply race. Use owned synthetic sessions until integration hardening is complete.

## Build and check

Rust 1.95+, a native C toolchain and Python 3.13 are required. Current application smoke scripts target Windows. No app binary is bundled.

```powershell
cargo build -p craftlink-broker --locked
python -m unittest discover -s tests -v
```

The broker accepts `PROJECT_ROOT [PORT]`; supply a random project bearer credential of at least 32 bytes on its first stdin line. Startup stdout provides its loopback address. Keep credentials out of Git, command lines and logs. See the [SDK](docs/SDK.md) and [architecture overview](docs/OVERVIEW.md).

`python scripts/smoke.py` runs real installed apps with fresh synthetic files/profiles under ignored `runtime/`, including crash, conflict, reopen, offline and relocation checks. It requires Python `psutil` for the suspended-process check. `scripts/live_smoke.py` additionally requires an explicitly supplied candidate FigCraft executable through `CRAFTLINK_FIGCRAFT_EXE`; follow the exact candidate revisions in the verification record. Never replace installed executables for testing.

## Collaboration and status

Read [CONTRIBUTING.md](CONTRIBUTING.md), [scoped follow-up drafts](docs/CONTRIBUTOR_ISSUES.md) and [verification](docs/VERIFICATION.md). Launcher integration, additional adapters, richer semantic fidelity, stable schemas/migrations, per-application permissions and production rollout remain unfinished. Existing upstream owners include craft-libs [command hooks #431](https://github.com/storytold/craft-libs/pull/431), [IPC #433](https://github.com/storytold/craft-libs/pull/433) and [document linking #59](https://github.com/storytold/craft-libs/issues/59); this prototype does not replace those proposals.

Source-only contribution. Binary redistribution notices have not received a complete all-target review. Original private implementation history and raw machine-local evidence are intentionally excluded from this clean publication repository.

MIT OR Apache-2.0: [LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE), [NOTICE](NOTICE). App names imply no endorsement or trademark license.
