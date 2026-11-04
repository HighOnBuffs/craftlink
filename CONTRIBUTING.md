# Contributing to CraftLink

CraftLink is an experimental integration project. Start with one [scoped issue draft](docs/CONTRIBUTOR_ISSUES.md); the shared core is proposed in `storytold/craft-libs#601`. Read the [overview](docs/OVERVIEW.md) and [SDK contract](docs/SDK.md) before changing protocol or persistence behavior.

## Small, reviewable changes

- Work on a branch. Describe the problem, changed behavior, supported fidelity, exact checks run and remaining limits in your pull request.
- Keep native engines and formats intact. Unsupported operations must return capability errors or disclose a fallback. Never silently overwrite concurrent edits.
- Keep shared contracts independent of app names and UI frameworks. Extend adapters through explicit capabilities; preserve UUIDs, immutable snapshots and idempotent replay.
- Use synthetic documents and isolated app profiles. Do not alter installed binaries, user projects or unrelated sessions. Never commit credentials, native test documents, build outputs or local caches.
- Preserve the existing evidence and commits. New results belong in a separate, clearly dated record; do not relabel old evidence as current validation.

Changes to an individual Craft app or launcher belong in its repository and must follow that repository's current AGENTS/contributor rules. Link the exact upstream revision or patch in the CraftLink pull request. Do not assume the audit clones under `upstream/` exist for another contributor.

## Focused verification

Rust 1.95+, a native C toolchain and Python 3.13 are the initial development prerequisites. On Windows the Rust build uses MSVC. Prefer checks matching the change:

```powershell
cargo fmt -p craftlink-broker -- --check
cargo test --workspace --locked
cargo clippy -p craftlink-broker --all-targets --locked -- -D warnings

# Shared core native/wasm checks are recorded in craft-libs PR #601.
```

For broker/SDK changes, first build `cargo build -p craftlink-broker --locked`, then run `python -m unittest discover -s tests -v`. Those tests launch broker/reference subprocesses and retain small fixtures under ignored `runtime/`; they do not prove a native adapter works.

Native adapter acceptance requires actual compatible app processes. The opt-in `./scripts/verify.ps1 -NativeSmoke` also runs broader checks and requires Windows, PowerShell, the documented Craft versions and Python `psutil`. Run it only when relevant and report versions, results and limitations. Do not launch it for documentation-only edits. Candidate live integration has a separate opt-in smoke described in the verification record.

## Licensing and reports

Contribute only material you have permission to submit under MIT OR Apache-2.0, retaining third-party notices and provenance. No contributor agreement or DCO process is currently established. Do not copy proprietary app code, artwork or user documents. Changes to `vendor/` need an exact upstream revision, license review and focused regression evidence.

Before opening an issue, remove private paths, credentials and user data. Use a minimal synthetic reproduction. Do not put exploitable credential material in a public report; maintainers must establish a private security contact before accepting confidential reports. The original private history and raw local evidence are excluded from this source-only repository. Binary redistribution requires a separate complete dependency-notice review.
