# Aggregate sources + browser-export discovery — design

**Scope:** Add an optional front-end to `bitwarden_vault_cleanup.py` that, on launch, detects
the major browsers installed on the machine and offers to **aggregate** passwords from them
(plus the user's Bitwarden export) into one cleaned, import-ready vault. Aggregation is done the
safe way: the tool **never reads or decrypts any browser credential store** — it detects which
browsers are *installed*, guides the user through each browser's own export, ingests the
resulting export files, converts them to Bitwarden items, and feeds everything into the existing
deduplication algorithm unchanged.

This is the entry-level, file-based tool (the advanced sibling lives at
[bw-vault-tools](https://github.com/no84by/bw-vault-tools)). Aggregation fits here because this
tool already consumes export files and its whole purpose is dedup/merge.

**Coherence with the entry-level positioning.** Consolidating scattered browser passwords into
one vault is an *onboarding* need — exactly the non-technical audience this tool serves. The
feature preserves the brand because it is **optional and skippable**: it stays one file, requires
no third-party dependencies (stdlib `csv`/`glob`/`uuid` only), and the classic "pass a Bitwarden
JSON and clean it" path is unchanged. The complexity is opt-in, behind the launch prompt.

**Terminal UI — optional `rich`, stdlib fallback.** All user-facing front-end output goes through
one tiny `ui` abstraction. If `rich` is importable, the front-end renders coloured tables/panels
and nicer prompts; if not, it falls back to plain stdlib `print`/`input`. `rich` is therefore a
**soft, optional** dependency — never required, never installed by the tool — so the single-file,
download-and-run, zero-required-deps story holds. Centralising both render paths behind the `ui`
object keeps it to one abstraction rather than scattered `if rich:` branches. (Note: this is a
*terminal* UI; the web-oriented frontend-design tooling does not apply.)

## Cornerstones (non-negotiable)

> **1. Presence-only browser detection.** Detection checks whether a browser is installed
> (profile directory or binary on PATH). It does **not** open, read, copy, or decrypt any
> browser password store, `Login Data`, `key4.db`, Keychain item, or cookie file. The malware
> path assessed and rejected on 2026-05-31 stays rejected.

> **2. Ingest only user-produced exports.** The tool reads only files the user exported
> themselves (a Bitwarden JSON, or a browser's own "Export passwords" CSV). It guides the
> export; it never performs it on the user's behalf by touching the store.

> **3. Reuse the dedup algorithm verbatim.** Converted items from every source flow into the
> existing `deduplicate()`. Identical entries collapse; app/web URI variants merge;
> entries that differ in password are all retained (the grouping key includes the password).
> No new cross-source conflict policy is introduced — the dedup is the conflict policy.

> **4. v2.1 output guarantees apply to the merged result.** `validate_vault` on every ingested
> file, 0600 output, no plaintext-password printing, preserve-non-deduplicable items.

## User flow

```
$ python bitwarden_vault_cleanup.py            (no args, or --aggregate)
  -> detect installed browsers (presence only)
  -> scan ~/Downloads and CWD for existing exports (content-sniff)
  -> "Detected: Firefox, Chrome, Edge. Found: bitwarden.json, Chrome.csv.
      Aggregate all of these into one cleaned vault? [Y/n]"
  -> for each chosen source NOT already found:
       print that browser's exact export steps
       watch ~/Downloads for a new CSV (mtime after the prompt) OR accept a pasted path OR skip
  -> ingest every collected file -> convert to Bitwarden items (tag origin)
  -> existing clean_entries + deduplicate + write_output -> one cleaned JSON (0600)
```

If the user declines aggregation (or passes a vault path the classic way), the tool behaves
exactly as today — this front-end is additive and skippable.

## Components (additive; single file preserved)

| Function | Responsibility | Reads credential stores? |
|---|---|---|
| `detect_browsers()` | Return the set of installed major browsers by checking known profile dirs / binaries per OS. | **No** — existence check only |
| `scan_for_exports(dirs)` | Classify files in `~/Downloads` + CWD by content sniff → `[(path, kind)]`. `kind` ∈ {bitwarden_json, chromium_csv, firefox_csv, safari_csv}. | No — reads only files the user exported |
| `export_instructions(browser)` | Return the verbatim export steps for a detected browser. | No |
| `collect_source(browser, watch_dir)` | Print steps, watch for a new matching CSV / accept a pasted path / allow skip. | No |
| `csv_to_items(path, kind)` | Map a known CSV schema → Bitwarden login items (origin tag in a field). | n/a (parses the export) |
| `aggregate_sources(found, chosen)` | Orchestrate detect→offer→collect→convert; return a merged `items` list. | No |
| `clean_entries` / `deduplicate` / `write_output` | **Unchanged.** Consume the merged items. | n/a |

## Source formats + mapping

- **Bitwarden JSON** — native; items used as-is (already handled).
- **Chromium CSV** (Chrome/Edge/Brave/Opera/Vivaldi share it): header `name,url,username,password,note`.
- **Firefox CSV**: header includes `url,username,password,httpRealm,formActionOrigin,guid,timeCreated,timeLastUsed,timePasswordChanged`.
- **Safari CSV**: header `Title,URL,Username,Password,Notes,OTPAuth`.

`csv_to_items` maps each to a Bitwarden login item:
`{id: <fresh uuid4>, type:1, name: <name|title|host(url)>, folderId: null,
login:{uris:[{uri:url,match:null}], username, password, totp: <otp if present else null>,
fido2Credentials: []}, notes: <note + "\n[source: <browser>]">}`.

**Coherence note — `id` is required.** The existing `deduplicate()` keys on `entry['id']`
(grouping, `ungrouped` re-add) and the v2.1 preservation logic round-trips by id, so every
converted CSV row **must** carry a fresh `uuid4` id. Browser CSVs have none, so `csv_to_items`
generates one per row. Dates (`revisionDate`/`creationDate`) are absent in browser exports; the
dedup scoring reads them via `.get(..., "")` (empty sorts consistently), and Bitwarden assigns
real ids/dates on re-import — so converted items need only `id` to flow through the algorithm.

Rows missing url/username/password are still emitted (preserve-everything; a row with no URL
lands in the no-URI passthrough). Classification is by **header signature**, not filename, so a
renamed file still works; an unrecognized CSV is reported and skipped (never guessed).

## Detection method (per OS, presence only)

- **Linux:** profile dirs under `~/.mozilla/firefox`, `~/.config/{google-chrome,microsoft-edge,BraveSoftware,opera,vivaldi}`; or binary on PATH.
- **macOS:** `~/Library/Application Support/{Google/Chrome,Microsoft Edge,BraveSoftware,Firefox}`; Safari via `~/Library/Safari` (export is manual-only — instructions, no watch).
- **Windows:** `%LOCALAPPDATA%\{Google\Chrome,Microsoft\Edge,BraveSoftware,...}\User Data`, `%APPDATA%\Mozilla\Firefox`.
A browser counts as "installed" if its profile dir exists. We read directory existence only.

The **Downloads directory is resolved per-OS** (`%USERPROFILE%\Downloads` on Windows,
`~/Downloads` elsewhere), falling back to CWD if it does not exist. All scanning/watching uses
this resolved path plus CWD.

## Wait-for-export mechanics

`collect_source` records the start time, prints the steps, then polls `~/Downloads` (and CWD)
every ~1s for a CSV whose mtime is newer than start and whose header matches the expected kind.
On match it confirms the path with the user. The user can instead paste a path, or press a key
to skip that source. A bounded timeout (e.g. 3 min) falls back to "skip / paste path" so the run
never hangs. Non-interactive stdin (the v2.1 guard) disables the guided loop entirely and the
tool aggregates only already-found files.

## Error handling

- Unreadable / malformed CSV → report and skip that source (never abort the whole run).
- `validate_vault` still gates the Bitwarden JSON (encrypted-export refusal, etc.).
- Zero sources collected → fall back to the classic single-file behavior or exit with guidance.
- Safari / a browser with no automatable export → print manual steps, no watch.

## Testing

- `scan_for_exports` / `csv_to_items`: pure functions over fixture files — one fixture per CSV
  schema (chromium, firefox, safari) + a Bitwarden JSON + an unrecognized CSV (skipped). Assert
  correct `kind` classification and item mapping, including a row missing a URL (preserved).
- `detect_browsers`: point the probe at a temp dir tree with/without each profile dir; assert
  presence map. Never touches real browser data in tests.
- End-to-end: aggregate a Bitwarden JSON + a Chromium CSV with one overlapping identical login
  and one browser-only login → merged, deduped output contains the union with the duplicate
  collapsed and the browser-only login added; differing-password rows both retained.
- The guided loop is exercised with an injected fake "watch" (no real browser/filesystem race).

## Non-goals

Reading or decrypting any browser credential store (rejected 2026-05-31 — see the feasibility
assessment: Chrome App-Bound Encryption / Keychain ACLs / infostealer optics). Importing
passkeys (not exportable). First-class support for non-browser password managers (the generic
CSV mapper may handle some incidentally; not a goal). Pushing to Bitwarden directly (still
file-out → user re-imports).

## Risks & assumptions

- **CSV schemas drift.** Browsers may change export columns; classification by header signature
  + skip-on-unknown contains the blast radius (report, don't guess).
- **Downloads watch races.** A pre-existing CSV could match; mtime-after-prompt + explicit
  user confirmation mitigates. Pasted-path is always available as the deterministic fallback.
- **Aggregation grows the vault, then dedup shrinks it** — on-brand for this tool; the summary
  reports per-source counts so the user sees what came from where.
