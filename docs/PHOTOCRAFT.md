# PhotoCraft read-only inspection reference

`sdk/photocraft_readonly.py` reads layer IDs, names, native kinds and hierarchy from
an explicitly supplied authenticated PhotoCraft control session. It registers
`manifests/photocraft-readonly.json` through the existing SDK without any broker or
core application switch. This is live source-backed metadata inspection. It does
not transfer pixels, masks, effects, previews, editable links or native snapshots
to the shared store. Native documents remain owned by PhotoCraft.

The installed binary tested was PhotoCraft 0.20.1 (`327c4cc82`, 2026-11-03).
Source contracts were checked at that revision in
[the control protocol](https://github.com/storytold/photocraft/blob/327c4cc82/docs/control-protocol.md)
and against the installed command catalog. Current upstream main was separately
observed at `8e82c0e728ee03eb0ce7e5d12289f98bae1595c9`; this does not prove that
version is installed. No upstream source, artwork or binary is copied here.

Use an owned synthetic document/profile. Start PhotoCraft with `--new-instance`,
an explicit loopback `--control` port, `--control-token-file` and the native
automation read/write roots for your fixture directory. Give the token file
private filesystem permissions. Keep the selected document active during a read.
The adapter never opens/saves files or invokes native edits; fixture setup uses
PhotoCraft's existing root-confined `app.open`/`app.save` methods.

Run `examples/photocraft_layers.py ADDRESS PORT TOKEN_FILE DOCUMENT_UUID` with the
broker credential supplied on stdin. Persist the document UUID separately and
reuse it when reopening/relocating that same native document; give independent
documents new UUIDs. UUIDv5 maps that namespace and each native layer ID to a
stable object ID. This is not automatic document discovery, copy detection or
protection against future native ID reuse. Native endpoint errors/credentials are
not echoed. Replies are bounded to 1 MiB, trees to 10,000 layers/64 levels, and
socket inspection to a five-second deadline. Oversized/unsupported inputs fail
explicitly.

The manifest has `write: false` and no editable properties. Local writes and
broker commits under this registered manifest are rejected with `capability`.
Project bearer credentials remain trusted-project access, including registration;
this does not introduce per-adapter credential isolation. Publishing an owned
read-only snapshot needs a distinct, reviewed capability before canonical asset
library entries or dependencies can be claimed.

Verification: three contract tests and five actual PhotoCraft/broker checks
passed, including nested hierarchy, separate-process SDK registration, save/reopen
identity, bad native credential, unavailable source, local/broker write refusal,
unchanged native document hashes, and standalone create/save after inspection.
Reproduce with `python -m unittest discover -s tests -p test_photocraft_readonly.py -v`,
then `python scripts/photocraft_smoke.py` after building the broker. The smoke owns
fresh native processes/files/profiles, deletes transient token files and stops
only its processes. Non-Windows runtime and compatibility beyond the tested native
catalog are unverified. Follow-up: [PhotoCraft #11321](https://github.com/storytold/photocraft/issues/11321).
