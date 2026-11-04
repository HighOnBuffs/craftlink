param([switch]$NativeSmoke)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:CARGO_HOME = Join-Path (Get-Location) '.cargo-home'
function Assert-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit $LASTEXITCODE" } }
cargo fmt -p craftlink-broker -- --check
Assert-Exit
cargo test --workspace --locked
Assert-Exit
cargo clippy -p craftlink-broker --all-targets --locked -- -D warnings
Assert-Exit
cargo build -p craftlink-broker --locked
Assert-Exit
python -m unittest discover -s tests -v
Assert-Exit
if ($NativeSmoke) {
    python scripts/smoke.py
    Assert-Exit
}
