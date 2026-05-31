# Compatibility

## Bitwarden export schema support

| `bw` / Bitwarden era | Item types | Passkeys | SSH keys | Status |
|---|---|---|---|---|
| ~2025.x (v1.x of this tool) | 1–4 | n/a | n/a | superseded by v2.0 |
| **2026.x (v2.0+)** | **1–5** | **detected + guarded** | **type 5, passed through** | supported |

v2.0 (2026-05) updates this tool for the Bitwarden 2026.x JSON export:

- **SSH keys (item type 5)** are labelled, counted, and passed through untouched. v1.x
  bucketed them as "Unknown Type".
- **Passkeys (`login.fido2Credentials`)** are detected and **excluded from deduplication**, so
  a merge can never drop a passkey-bearing login. Affected items are reported with a warning.

## Known Bitwarden limitation — passkeys and export

The Bitwarden CLI / JSON export does not reliably round-trip passkeys
(`login.fido2Credentials`); see [bitwarden/clients#6925](https://github.com/bitwarden/clients/issues/6925).
This tool never drops a passkey itself, **but the recommended purge + reimport step cannot
restore a passkey that your export never captured.** Before purging:

1. Confirm your export actually contains the `fido2Credentials` for your passkey logins, or
2. be prepared to re-enrol those passkeys after import, or
3. use an in-place tool that does not purge — see below.

## Successor project

For in-place delta application (no purge + reimport) and two-way vault sync, see
[**bw-vault-tools**](https://github.com/no84by/bw-vault-tools). The deduplication algorithm in
this script lives on there as `identity.py`.

## Browser aggregation — what it does and does not touch

The optional `--aggregate` mode detects installed browsers by directory existence only and
ingests password CSVs that YOU export via each browser's built-in exporter. It never reads,
copies, or decrypts `Login Data`, `key4.db`, the macOS Keychain, or any other credential store.
Supported export CSVs: Chromium (Chrome/Edge/Brave/Opera/Vivaldi), Firefox, Safari.
