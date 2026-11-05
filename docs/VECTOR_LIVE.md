# Native live slice — baseline and reliability continuation

## Current candidate — 2026-11-05

Use VectorCraft feature `9c9e1f47cd02a757010c258a386748ce384be846`, which preserves
the original feature and merges upstream `7436b4be5` without rewriting history.
Apply this revision's `vectorcraft-native-auth-test.patch`; the resulting native
source is the isolated test composition `b5a79129cc6966f0f83c780bb3791d46f08c6778`.
The patch retains existing auth ownership/licensing and upstream graceful socket
close behavior. FigCraft's pin and build/run commands below are unchanged.

The original 2026-11-04 evidence below is historical. To reproduce that exact
baseline, use consumer commit `e590382bdba2c3e1b386d05546eb63077d019e64`, including
its original authentication patch and smoke script.

New scope: guarded background document routing for name/opacity and native byte
snapshots, with no foreground tab/tool changes. UIDs survive tab reordering within
the process; closed/mismatched targets fail explicitly. Direct native interaction
commits notify the shared change bus once, coalescing preview samples. This does
not add geometry/transform interoperability or in-progress preview streaming.

Executed on Windows: 6 engine change-feed tests, 6 UI routing/guard tests,
26 native socket/auth tests, 5 consumer subprocess regressions, engine WASM
check, 28-crate layering check and the candidate desktop build passed. The
upstream merge alone also passed 58 selected engine regressions. Strict native
Clippy still fails on unchanged `drop_non_drop` at cleanup/text.rs:1007 and
fonts.rs:626; the diagnostic run allowing only that lint passed. No lint policy
or acceptance assertion was weakened. Full workspace CI/non-Windows runtime
were not run.

The real authenticated two-app smoke passed **13 checks**: the original
live/recovery/auth/history/reopen checks plus both background links with both
foreground tabs unchanged, projection while an unrelated native drag remains
pending, mismatched-target rejection, and a native 25-sample pointer drag with
exactly one invalidation/undo step and geometry-preserving undo/redo.
Single-run dispatch-to-observation samples (not percentiles):

| Operation | ms |
| --- | ---: |
| Unsaved VectorCraft to FigCraft | 70.73 |
| Unsaved FigCraft to VectorCraft | 63.03 |
| Background FigCraft to VectorCraft | 72.95 |
| Background VectorCraft to FigCraft | 79.87 |
| Native 25-sample drag commit and observation | 31.67 |

Retained failures: a test imported a private NodeId re-export; the auth test
composition needed the new graceful-close socket fixture authenticated; the
first smoke used `select` instead of catalog ID `selection`. Each was corrected
and its focused check rerun. The final smoke stopped all owned processes.

Remaining safety boundary: target-document pending interactions and undo groups
still reject writes; automatic retry after transient busy/revision failures
needs hardening so a temporary refusal cannot freeze a binding as conflicted.
Multiple tabs in both applications were tested; multiple simultaneously running
instances of the same product were not. Broker credentials and native auth
adoption remain separately owned. Core automated storage/history review findings
on #601 are pending investigation; these results are not power-loss certification.

## Original verified baseline — 2026-11-04

Native seam: [VectorCraft PR #5689](https://github.com/storytold/vectorcraft/pull/5689),
commit `f6bed625cebc27785586c7080bec8b33b8c52fce`, based on upstream
`18490471a`. It reuses the proposed `craft-command::ChangeBus` at
`61db4a13ddd42a3727c8802168d90a0a2dafb9de` ([#431](https://github.com/storytold/craft-libs/pull/431)).
Those proposals are unmerged. Only rectangle name/opacity semantic links are
accepted; native documents/snapshots retain other features without exposing them
as editable conversions.

## Reproduce

In an isolated VectorCraft clone, fetch `craftlink/native-live` from
`https://github.com/HighOnBuffs/vectorcraft` and create a candidate at the exact
commit above. Apply [vectorcraft-native-auth-test.patch](vectorcraft-native-auth-test.patch),
then `cargo build -p vectorcraft --locked`. The patch composes only native auth
from existing [#4623](https://github.com/storytold/vectorcraft/pull/4623), commit
`7613c15245af5bf6b5bdc28b0a04ada6515cc6bb`, by @mockydevs. Its wire protocol,
token storage and socket tests are reused; callback signatures are adapted. It
does not duplicate that upstream contribution or claim its CLI integration.
Attribution/license: [NOTICE](../NOTICE), [VectorCraft MIT](licenses/vectorcraft-LICENSE-MIT).
Local test composition was `a430ece13c0dc72a961bfda52175b831be359b0d`;
the published feature plus supplied patch reproduces the same native source.

Build the authenticated FigCraft candidate as described in [VERIFICATION.md](VERIFICATION.md):
feature `f3214ddd10bd2fd57420d7021e184cee69ed1695` plus its attributed auth test
patch (local composition `6609fd2b9a1b7538e93421500f82e7f1a408ee10`).
Set `CRAFTLINK_VECTORCRAFT_EXE` and `CRAFTLINK_FIGCRAFT_EXE` to those isolated
executables. Build this consumer's broker with `cargo build -p craftlink-broker --locked`,
run `python -m unittest discover -s tests -v`, then `python scripts/vector_live_smoke.py`.
The script requires both candidates, creates synthetic documents/profiles and
stops only its own processes. Never overwrite installed applications.

## Results actually executed

- Four engine invalidation tests; four UI guard/snapshot tests; 26 native
  authentication/control socket tests passed. An earlier broad name filter also
  passed 62 existing engine regressions. No full workspace suite ran.
- Native candidate build, source-only feature bin/tests compile check, and actual
  engine `--no-default-features --target wasm32-unknown-unknown` check passed.
- Strict library Clippy failed on unchanged upstream `drop_non_drop` in
  `cmd/addons/cleanup/text.rs:958` and `cmd/fonts.rs:626`. With only that lint
  allowed, the same focused check passed. The upstream files/lint policy were not
  modified. Strict all-target consumer broker Clippy passed without allowances.
- Five broker/SDK subprocess tests passed, including a synthetic A→B→A snapshot
  race and persisted pending-receipt recovery fixture. These are unit/integration
  regressions, separate from actual native acceptance.
- Ten real two-candidate checks passed: unsaved propagation both ways; unchanged
  native files; duplicate delivery; native VectorCraft undo/redo; stale guard
  rejection without revision mutation; missing/wrong auth for inspect/edit;
  managed undo/redo; broker termination/restart with unsaved source recovery;
  both app reopens on the same ports with identity/live updates; standalone
  foreground save and inactive-document guard rejection.
- One successful small-document run measured **78.56 ms VectorCraft→FigCraft**
  and **61.63 ms FigCraft→VectorCraft**. These include native command dispatch and
  verification round trips, and are not percentiles or a throughput benchmark.
- Existing installed-app saved-file smoke passed all 14 checks: 176.59/168.79 ms
  forward/reverse and 16.02 ms commit reply while receiver suspended. The script
  now waits for the acknowledged projection before the next local edit, preserving
  its late-event regression. Stock endpoints still lack conditional safety.

Failures retained locally led to concrete fixes: no-path copy incorrectly opened
a Save dialog; FigCraft copy bookkeeping needed guarded revision accounting;
an interrupted pending projection was misclassified as a new native edit; and
the reopen test closed before background Save reached disk. No failed run is
counted as successful evidence. Raw runtime data remains ignored and unpublished.

## Shared owners and limits

[IPC #433](https://github.com/storytold/craft-libs/pull/433) owns local sockets,
discovery and push subscriptions. This slice bridges the existing native control
worker and shared command bus, without adopting a second discovery/transport.
[ABI #432](https://github.com/storytold/craft-libs/pull/432) / [SDK #455](https://github.com/storytold/craft-libs/pull/455)
retain guest manifests, `link.call` and `link.exec` permission gates. Native
preconditions confer no plugin privileges. Core storage remains proposed in #601.

Direct gesture callbacks, collaboration writes and mutations outside successful
outer command dispatch remain uncovered. VectorCraft routing is active-document
only; native IDs/revisions are scoped to the authenticated app launch and must be
refreshed on reconnect. Live placement/lifecycle, per-app broker credentials,
non-Windows runtime, complete native CI and binary redistribution notices remain
open. Tracking: [guards #5687](https://github.com/storytold/vectorcraft/issues/5687),
[invalidations #5688](https://github.com/storytold/vectorcraft/issues/5688).
