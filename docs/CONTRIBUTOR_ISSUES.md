# Contributor work and upstream tracking

The scopes below describe small contributions. Check their current public tracking before starting, and follow the target repository's contributor rules. Implemented portions remain proposals until upstream review and merge.

- VectorCraft hooks/conditional writes: [#5675](https://github.com/storytold/vectorcraft/issues/5675).
- FigCraft events/conditional execution: [PR #1995](https://github.com/storytold/figcraft/pull/1995). Native auth remains owned by existing [PR #1473](https://github.com/storytold/figcraft/pull/1473); isolated composition is documented in [verification](VERIFICATION.md).
- PhotoCraft read-only layer adapter: [#11321](https://github.com/storytold/photocraft/issues/11321). The [metadata inspection reference](PHOTOCRAFT.md) is now verified. Publishing read-only snapshots still needs a separate capability from semantic write permission.
- Launcher read-only status: [PR #1239](https://github.com/storytold/craft-launcher/pull/1239), verified as documented; broader discovery/asset browsing remains open.
- Solid sRGB fill: [#1](https://github.com/HighOnBuffs/craftlink/issues/1).

Shared core boundary: [craft-libs #600](https://github.com/storytold/craft-libs/issues/600) / [PR #601](https://github.com/storytold/craft-libs/pull/601). Craft Anything generation seam: [#852](https://github.com/storytold/craft-anything/issues/852); its roadmap-claim/draft-PR contribution gate must precede host changes.

## 1. Emit unsaved rectangle-property events in VectorCraft

**Problem:** CraftLink observes saved files; a native name/opacity edit stays invisible until save.

**Scope:** Add an opt-in document-property event hook in VectorCraft for committed `object.setProps` name/opacity edits and native undo/redo. Expose a bounded sequence cursor through its control protocol. Keep the existing save-event fallback and other property types unchanged.

**Start:** VectorCraft `crates/engine/src/cmd/object.rs`, its control server and control-protocol documentation at the revision in [upstream source](https://github.com/storytold/vectorcraft). CraftLink consumer boundary: `crates/broker/src/native.rs`.

**Acceptance:** A focused upstream test receives one revision-tagged event after an unsaved name/opacity edit and corresponding undo/redo; inspecting or saving unchanged data adds none. Cursor overflow is explicit. Include a synthetic running-app trace showing the event before any file save. Submit the upstream patch and consumer contract, without claiming completed broker subscription integration.

## 2. Add opt-in authenticated conditional property writes in FigCraft

**Problem:** The native port lacks authentication and a conditional edit primitive, so broker authentication alone cannot close the native inspect/apply race.

**Scope:** Add an explicitly enabled authenticated control mode and one conditional name/opacity write operation in FigCraft. Receive the credential privately, use an engine-owned document revision precondition, and check that precondition in the same engine mutation as the property write. Preserve existing standalone behavior. Broker integration is a follow-up.

**Start:** FigCraft `apps/figcraft/src/control_server.rs`, `crates/ui-egui/src/control.rs`, engine `node.set` implementation and control-protocol docs. Use current upstream source to identify the exact revision mechanism; do not assume the session ID is a durable document revision.

**Acceptance:** Wrong/missing credentials cannot inspect or mutate the opted-in endpoint. A stale precondition leaves the document and history unchanged; one valid precondition applies exactly once. Supply focused auth/race tests and an isolated real-app trace. No credential appears in logs or command-line arguments.

## 3. Add a read-only PhotoCraft layer inspection adapter

**Problem:** No verified native integration exists beyond the initial two apps.

**Scope:** Inspect the installed PhotoCraft command catalog/source, then implement a read-only adapter example enumerating native layer IDs/names and explicit capability/fidelity metadata. Do not add write support, placement or preview conversion in this issue; do not special-case PhotoCraft in Core.

**Start:** [SDK.md](SDK.md), `examples/generated_app.py`, `sdk/craftlink.py`; verify PhotoCraft's actual native inspection/MCP interface before selecting commands.

**Acceptance:** Register the adapter through the SDK, inspect a synthetic layered native document in a real PhotoCraft process and retain the same layer identity after save/reopen. Verify a requested edit returns an explicit read-only capability error. Record exact app version and commands; leave write support unclaimed.

## 4. Show existing CraftLink binding status in the launcher

**Problem:** Users cannot inspect a connected project's link status through the native launcher.

**Scope:** Add one read-only project binding-status section to the launcher's existing app details view. Reuse its app catalog/detection and CraftLink `bindings` API. Connect to an explicitly supplied running broker; no new installer, service lifecycle, automatic discovery or asset browser.

**Start:** Launcher `crates/core/src/catalog.rs`, `crates/native/src/detect.rs` and current native UI details view. Broker operation: [SDK.md](SDK.md) `bindings`. Obtain the project credential through an appropriate private native input; never persist it in plain settings.

**Acceptance:** Show application, applied revision and current/stale/conflicted/missing/frozen status for a synthetic binding. A stopped broker or rejected credential produces a recoverable empty/error state; existing launch/install workflows remain intact. Include native UI inspection and focused state-mapping tests. Follow launcher localization rules.

## 5. Define and test an optional solid-sRGB rectangle-fill contract

**Problem:** Rectangle placement currently preserves bounds and synchronized name/opacity, but does not transfer fill.

**Scope:** Document an additive, capability-negotiated solid sRGB fill property and implement conversion helpers for the two existing profiles. Keep gradients, spot colors, profiles, patterns and multiple fills outside the editable contract. Do not change the default verified synchronization path in this issue.

**Start:** `manifests/`, the shared `craft-link-core` contracts, `crates/broker/src/native.rs`, and each app's actual paint command schemas.

**Acceptance:** Focused conversion tests round-trip representative solid colors and reject unsupported paints explicitly. Existing name/opacity-only manifests continue to negotiate unchanged. Provide a synthetic real-app read/apply/read trace for each conversion helper, document alpha handling and preserve original native snapshots. Enabling fill propagation is a later reviewed change.
