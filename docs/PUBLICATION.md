# Source publication boundary

This is a new clean source repository. It contains the reviewed broker, SDK, examples, manifests, synthetic tests, licenses and public-facing documentation. Its shared core is an exact git dependency on the public craft-libs contribution. Original private commit ancestry, local handoff/inventory/audit, raw workstation evidence, native documents, credentials, caches, binaries and cloned upstream working trees are excluded.

The FigCraft authentication test patch is attributed upstream code under MIT; its license is preserved separately. The core's atomic writer remains owned by craft-libs, not vendored again. Project source is MIT OR Apache-2.0. Dependency declarations/checksums stay in Cargo.lock. This review authorizes source collaboration only; a complete all-target dependency/advisory/notices review is still required before binary distribution.

Publishing this repository and draft PRs does not imply maintainer approval, official rollout or a production guarantee. Follow-up integration placement is subject to review in craft-libs #600. No upstream default branch is pushed and no PR is self-merged.
