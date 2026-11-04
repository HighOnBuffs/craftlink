# Verification — 2026-11-04

Source-only experimental contribution. The original local repository/commits and raw machine-local evidence are preserved separately, not published. No application or broker binary is distributed here.

## Shared core extraction

[craft-libs PR #601](https://github.com/storytold/craft-libs/pull/601), commit `46d38608042c17ebaf5aaa9bf82bc0df61fde68f`:

- `cargo test -p craft-link-core --features native --locked`: 13 passed (2 contracts + 11 native). The deliberately ignored crash helper is explicitly spawned by its parent test; an fsynced marker proves it reaches the actual precommit abort.
- Strict `--all-targets` Clippy for this crate passed.
- `--no-default-features --target wasm32-unknown-unknown` compilation passed.
- Formatting of the new crate passed. No full workspace suite, Unix runtime, macOS runtime or WASM app integration was run. The Unix-only symlink regression was not run on Windows.

## Native engine/control changes

[FigCraft PR #1995](https://github.com/storytold/figcraft/pull/1995), feature commit `f3214ddd`:

- 4 `link_revision_tests`, 12 `events_tests`/batch regressions and 4 `control::document_tests` passed.
- Strict library Clippy for `figcraft-engine`/`figcraft-ui-egui` passed. Full app CI was not run.
- Candidate executable built from the isolated feature branch plus the native authentication test composition below. Installed apps were not overwritten.

Real running candidate FigCraft and installed VectorCraft verified: unsaved source name/opacity changes without changing the saved file's hash; reverse guarded updates while the receiver stays unsaved; stale native revision rejection; mandatory native auth; duplicate notification handling; live managed undo/redo; native save/reopen identity; standalone editing. Eight checks passed. One small-document sample measured 52.87 ms unsaved forward and 89.35 ms saved reverse; these are not percentiles or a broad performance claim.

## Reproduce the authenticated native candidate

Authentication belongs to existing [FigCraft PR #1473](https://github.com/storytold/figcraft/pull/1473), commit `c59b50da54d9fdc3a0146db39f293c0a9e4a858b`. The full older patch conflicts with current app/client code. [figcraft-native-auth-test.patch](figcraft-native-auth-test.patch) composes only its native-server logic with the current server signature and settings-directory owner, for isolated testing. It does not duplicate that contribution in PR #1995 or claim its full client/test coverage. Source attribution/license: [NOTICE](../NOTICE), [FigCraft MIT license](licenses/figcraft-LICENSE-MIT).

In an isolated FigCraft clone, fetch the feature branch from `https://github.com/HighOnBuffs/figcraft`, create a new branch at `f3214ddd`, apply the test patch and build `cargo build -p figcraft --locked`. Set `CRAFTLINK_FIGCRAFT_EXE` to that candidate executable and run `python scripts/live_smoke.py` from this consumer repository. A clean candidate must generate its own native token file; live mode fails closed without it. The test owns fresh native files/profiles and stops only its processes. Do not use user documents.

## Broker/SDK and saved-file path

Four subprocess tests cover blocking replay/idempotency, permission/schema/path rejection, actual stdio MCP + future-app registration, and metadata availability while a native request stalls. Native I/O is a separate worker, not part of the metadata lock.

`scripts/smoke.py` tests two real installed apps: placement, saved propagation/reverse edit, native undo/redo, save/close/reopen identity, replay, retained unsaved conflict snapshots, optimistic rejection, bad broker credential, offline catch-up, broker kill between durable commit/projection, missing-file relocation, third reference process registration and standalone workflow. A suspended receiving process must not prevent the durable commit reply or head inspection. Raw outputs stay under ignored `runtime/`.

The clean consumer also passed all four subprocess tests, strict broker Clippy, 14 real saved-file checks and eight real candidate-live checks. Its small-document samples measured 171.29/138.27 ms saved forward/reverse, 60.66/124.8 ms unsaved forward/guarded reverse, and a 2.71 ms commit reply while the receiver was suspended. These are individual smoke observations, not benchmarks.

## Optional launcher status

[Launcher PR #1239](https://github.com/storytold/craft-launcher/pull/1239), commit `393f0adaf66dae534d6fbe2db87c3e9135841c96`, adds a feature-gated read-only section in the existing native app details drawer. Three native client tests, three UI state/render tests, 37 localization tests, strict all-target core/native/UI Clippy, formatting, the desktop feature compile check, `cargo xtask wasm` (core + full web app), and an additional WASM UI feature check passed. No dependency or lockfile changed.

In an isolated launcher checkout at that commit, build:

```powershell
cargo build -p artcraft-launcher-native --example craftlink_status --features craftlink-status --locked
```

Set `CRAFTLINK_LAUNCHER_STATUS_EXE` to that example executable, build this consumer's broker, then run `python scripts/launcher_status_smoke.py`. The probe owns a real VectorCraft process and broker, reads the current binding, observes the source becoming unavailable and checks credential rejection. Three checks passed. It deletes the transient credential file and stops its own processes. The panel was separately rendered with egui_kittest and visually inspected.

Do not start an ordinary candidate launcher beside a production launcher: its singleton handoff is shared. The probe does not start that shell. Full launcher workspace CI, singleton lifecycle and non-Windows runtime are unverified. Connection inputs are transient; no automatic discovery, polling, installation, native editing or asset browser is included.

## PhotoCraft read-only reference

PhotoCraft 0.20.1 (`327c4cc82`) passed three contract tests and five actual native/broker checks via `scripts/photocraft_smoke.py`. The separate example process registered its read-only manifest and enumerated three layers with retained hierarchy. Save/reopen preserved caller-namespaced global/native IDs; invalid native auth and unavailable sources failed explicitly. Local edits, write negotiation and direct broker commits were rejected; native file hashes stayed unchanged. Native standalone layer creation/save still worked. No core/broker dispatch change was needed. [Scope and reproduction](PHOTOCRAFT.md).

Only rectangle name/opacity and initial axis-aligned bounds are accepted for bidirectional editing. PhotoCraft supports metadata inspection only. Arbitrary gestures, collaboration writes, VectorCraft unsaved events/conditional writes, additional semantic adapters and universal losslessness remain unsupported. Existing stock control ports retain their documented security limitations. Binary release dependency notices/all-target license review remain open.
