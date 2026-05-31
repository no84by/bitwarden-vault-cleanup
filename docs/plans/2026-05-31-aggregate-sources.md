# Aggregate Sources + Browser-Export Discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional launch front-end to `bitwarden_vault_cleanup.py` that detects installed browsers (presence only), offers to aggregate their passwords plus the Bitwarden export, guides each browser's own export, ingests the resulting files, and feeds everything into the existing dedup unchanged.

**Architecture:** Pure helpers (detect / classify / convert) plus one orchestrator (`aggregate_sources`) added to the existing single file. Converted items from every source flow into the unchanged `clean_entries`/`deduplicate`/`write_output`. Never reads or decrypts any browser store — detection is directory-existence only; ingestion is of user-produced export files.

**Tech Stack:** Python 3.7+ stdlib (`csv`, `glob`, `uuid`, `os`, `time`, `platform`). No *required* dependencies. **Optional** `rich` for a prettier terminal UI, with a stdlib fallback (soft dependency — never installed by the tool). `pytest` for tests (dev-only). Note: the web-oriented frontend-design tooling does not apply to a terminal UI.

**Repo:** `/home/xt8664/workspace/code/platform/bitwarden-vault-cleanup`, branch `feat/aggregate-sources`.
**Spec:** `docs/design/2026-05-31-aggregate-sources-design.md`.

---

## File Structure

All new code lands in the existing single file `bitwarden_vault_cleanup.py` (the tool's defining
property is "one file, download and run"). New pure functions are added near the existing
parsing helpers; the orchestrator is called from `main()` before the classic path. Tests are new
files (dev-only, not shipped to end users who just download the script).

```
bitwarden_vault_cleanup.py
  + get_ui()                 -> _RichUI() if `rich` importable else _PlainUI()
  + _PlainUI / _RichUI       one tiny render abstraction: heading/info/warn/confirm/ask/table/rule
  + BROWSERS                 module constant: per-browser profile dirs + export instructions
  + downloads_dir()          OS-aware Downloads path (+ CWD fallback)
  + detect_browsers(probe)   presence map by profile-dir existence (probe root injectable for tests)
  + classify_export(path)    content-sniff -> kind in {bitwarden_json, chromium_csv, firefox_csv, safari_csv, None}
  + scan_for_exports(dirs)   -> [(path, kind)]
  + csv_to_items(path, kind) -> [bw login item dicts] (fresh uuid id each)
  + export_instructions(b)   -> str (verbatim steps)
  + collect_source(...)      guided wait-for-export for one browser (clock + watcher injectable)
  + aggregate_sources(...)   orchestrate detect/scan/offer/collect/convert -> merged items list
  + main()                   call aggregation front-end before the classic flow (modify)
tests/                       NEW (dev-only): conftest + fixtures + test_aggregate.py
  conftest.py                ensures repo root import
  fixtures/chromium.csv firefox.csv safari.csv bitwarden.json random.csv
  test_aggregate.py
```

Tests import the script as a module: `import bitwarden_vault_cleanup as bvc`. This is now safe
because v2.1 wrapped execution in `main()` under `if __name__ == "__main__":`.

---

## Task 1: Test harness — import the script as a module + fixtures

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/chromium.csv`, `tests/fixtures/firefox.csv`, `tests/fixtures/safari.csv`, `tests/fixtures/bitwarden.json`, `tests/fixtures/random.csv`
- Create: `tests/test_aggregate.py`

- [ ] **Step 1: Create the import shim** — `tests/conftest.py`

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 2: Create fixtures**

`tests/fixtures/chromium.csv`:
```csv
name,url,username,password,note
Example,https://example.com,alice,pw1,hello
NoUrlRow,,bob,pw2,
```

`tests/fixtures/firefox.csv`:
```csv
url,username,password,httpRealm,formActionOrigin,guid,timeCreated,timeLastUsed,timePasswordChanged
https://site.org,carol,pw3,,https://site.org,{abc},0,0,0
```

`tests/fixtures/safari.csv`:
```csv
Title,URL,Username,Password,Notes,OTPAuth
MyBank,https://bank.test,dave,pw4,note4,
```

`tests/fixtures/bitwarden.json`:
```json
{"encrypted": false, "folders": [], "items": [
  {"id": "11111111-1111-1111-1111-111111111111", "type": 1, "name": "example.com",
   "notes": null, "login": {"uris": [{"uri": "https://example.com", "match": null}],
   "username": "alice", "password": "pw1", "totp": null, "fido2Credentials": []}}
]}
```

`tests/fixtures/random.csv`:
```csv
foo,bar,baz
1,2,3
```

- [ ] **Step 3: Smoke test the import** — `tests/test_aggregate.py`

```python
import bitwarden_vault_cleanup as bvc


def test_module_imports_without_running_main():
    assert hasattr(bvc, "deduplicate")
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd /home/xt8664/workspace/code/platform/bitwarden-vault-cleanup && python -m pytest tests/test_aggregate.py -v`
Expected: PASS (importing the module does not execute `main()` because v2.1 guards it).

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: harness + fixtures for aggregation"
```

---

## Task 2: `classify_export` — content-sniff a file's kind

**Files:**
- Modify: `bitwarden_vault_cleanup.py` (add `classify_export` after `load_vault`)
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_aggregate.py`:

```python
import os

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_classify_bitwarden_json():
    assert bvc.classify_export(os.path.join(FX, "bitwarden.json")) == "bitwarden_json"


def test_classify_chromium_csv():
    assert bvc.classify_export(os.path.join(FX, "chromium.csv")) == "chromium_csv"


def test_classify_firefox_csv():
    assert bvc.classify_export(os.path.join(FX, "firefox.csv")) == "firefox_csv"


def test_classify_safari_csv():
    assert bvc.classify_export(os.path.join(FX, "safari.csv")) == "safari_csv"


def test_classify_unknown_returns_none():
    assert bvc.classify_export(os.path.join(FX, "random.csv")) is None
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k classify -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'classify_export'`.

- [ ] **Step 3: Implement `classify_export`**

Add after `load_vault` in `bitwarden_vault_cleanup.py`:

```python
def classify_export(path):
    """Sniff a file's export kind by content (not filename). Returns one of
    'bitwarden_json', 'chromium_csv', 'firefox_csv', 'safari_csv', or None."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            head = f.read(4096)
    except OSError:
        return None
    stripped = head.lstrip()
    if stripped.startswith('{'):
        return 'bitwarden_json' if '"items"' in head else None
    first_line = head.splitlines()[0].lower() if head.splitlines() else ''
    cols = {c.strip().strip('"') for c in first_line.split(',')}
    if {'name', 'url', 'username', 'password'} <= cols:
        return 'chromium_csv'
    if {'url', 'username', 'password'} <= cols and 'httprealm' in cols:
        return 'firefox_csv'
    if {'title', 'url', 'username', 'password'} <= cols:
        return 'safari_csv'
    return None
```

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k classify -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): classify_export content-sniff"
```

---

## Task 3: `scan_for_exports` — find candidate files in given dirs

**Files:**
- Modify: `bitwarden_vault_cleanup.py`
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_scan_for_exports_finds_and_classifies(tmp_path):
    import shutil
    for fn in ("chromium.csv", "bitwarden.json", "random.csv"):
        shutil.copy(os.path.join(FX, fn), tmp_path / fn)
    found = bvc.scan_for_exports([str(tmp_path)])
    kinds = sorted(k for _, k in found)
    assert kinds == ["bitwarden_json", "chromium_csv"]   # random.csv (None) excluded
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k scan -v`
Expected: FAIL — no attribute `scan_for_exports`.

- [ ] **Step 3: Implement `scan_for_exports`**

```python
def scan_for_exports(dirs):
    """Return [(path, kind)] for files in `dirs` recognized as exports. Unknown files skipped."""
    seen = set()
    out = []
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(('.csv', '.json')):
                continue
            path = os.path.realpath(os.path.join(d, name))
            if path in seen:
                continue
            seen.add(path)
            kind = classify_export(path)
            if kind:
                out.append((path, kind))
    return out
```

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k scan -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): scan_for_exports"
```

---

## Task 4: `csv_to_items` — map a browser CSV to Bitwarden login items

**Files:**
- Modify: `bitwarden_vault_cleanup.py`
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_csv_to_items_chromium_maps_fields_and_assigns_uuid():
    items = bvc.csv_to_items(os.path.join(FX, "chromium.csv"), "chromium_csv")
    assert len(items) == 2
    a = items[0]
    assert a["type"] == 1
    assert a["login"]["username"] == "alice"
    assert a["login"]["password"] == "pw1"
    assert a["login"]["uris"][0]["uri"] == "https://example.com"
    assert a["login"]["fido2Credentials"] == []
    assert len(a["id"]) == 36 and a["id"].count("-") == 4   # uuid4
    assert "[source: chromium]" in (a["notes"] or "")


def test_csv_to_items_row_without_url_has_no_uris():
    items = bvc.csv_to_items(os.path.join(FX, "chromium.csv"), "chromium_csv")
    nourl = items[1]                       # the NoUrlRow fixture row
    assert nourl["login"]["uris"] is None
    assert nourl["login"]["username"] == "bob"


def test_csv_to_items_firefox_and_safari_columns():
    ff = bvc.csv_to_items(os.path.join(FX, "firefox.csv"), "firefox_csv")[0]
    assert ff["login"]["username"] == "carol" and ff["login"]["uris"][0]["uri"] == "https://site.org"
    sf = bvc.csv_to_items(os.path.join(FX, "safari.csv"), "safari_csv")[0]
    assert sf["login"]["username"] == "dave" and sf["name"] == "MyBank"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k csv_to_items -v`
Expected: FAIL — no attribute `csv_to_items`.

- [ ] **Step 3: Implement `csv_to_items`** (add `import csv` and `import uuid` to the top import block)

```python
# column maps: kind -> (name_col, url_col, user_col, pass_col, note_col, source_label)
_CSV_SCHEMA = {
    "chromium_csv": ("name", "url", "username", "password", "note", "chromium"),
    "firefox_csv": (None, "url", "username", "password", None, "firefox"),
    "safari_csv": ("title", "url", "username", "password", "notes", "safari"),
}


def _host(url):
    return normalize_uri(url) if url else ""


def csv_to_items(path, kind):
    """Map a recognized browser CSV to Bitwarden login items (one per row, fresh uuid id)."""
    name_c, url_c, user_c, pass_c, note_c, source = _CSV_SCHEMA[kind]
    items = []
    with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.DictReader(f)
        lower = {fn: (fn or '').strip().lower() for fn in (reader.fieldnames or [])}
        # build a case-insensitive accessor
        def get(row, col):
            if not col:
                return ''
            for orig, low in lower.items():
                if low == col:
                    return (row.get(orig) or '').strip()
            return ''
        for row in reader:
            url = get(row, url_c)
            name = get(row, name_c) or _host(url) or "(imported)"
            note = get(row, note_c)
            tag = f"[source: {source}]"
            notes = (note + "\n" + tag).strip() if note else tag
            items.append({
                "id": str(uuid.uuid4()),
                "organizationId": None,
                "folderId": None,
                "type": 1,
                "name": name,
                "notes": notes,
                "login": {
                    "uris": [{"uri": url, "match": None}] if url else None,
                    "username": get(row, user_c) or None,
                    "password": get(row, pass_c) or None,
                    "totp": None,
                    "fido2Credentials": [],
                },
            })
    return items
```

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k csv_to_items -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): csv_to_items (chromium/firefox/safari -> bw items)"
```

---

## Task 5: `BROWSERS` constant + `detect_browsers` (presence only)

**Files:**
- Modify: `bitwarden_vault_cleanup.py`
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing test** (inject a fake home root; no real browser data touched)

Append:

```python
def test_detect_browsers_presence_only(tmp_path, monkeypatch):
    # create a fake firefox profile dir under a fake linux home
    (tmp_path / ".mozilla" / "firefox").mkdir(parents=True)
    monkeypatch.setattr(bvc.platform, "system", lambda: "Linux")
    found = bvc.detect_browsers(home=str(tmp_path))
    assert "firefox" in found
    assert "chrome" not in found          # its dir does not exist
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k detect -v`
Expected: FAIL — no attribute `detect_browsers`.

- [ ] **Step 3: Implement `BROWSERS` + `detect_browsers`**

```python
# Presence-only detection: per-OS profile dirs (relative to the user's home / appdata).
# We check ONLY that the directory exists. We never open, read, copy, or decrypt any file in it.
BROWSERS = {
    "firefox":  {"linux": ".mozilla/firefox", "darwin": "Library/Application Support/Firefox",
                 "windows": "AppData/Roaming/Mozilla/Firefox"},
    "chrome":   {"linux": ".config/google-chrome", "darwin": "Library/Application Support/Google/Chrome",
                 "windows": "AppData/Local/Google/Chrome/User Data"},
    "edge":     {"linux": ".config/microsoft-edge", "darwin": "Library/Application Support/Microsoft Edge",
                 "windows": "AppData/Local/Microsoft/Edge/User Data"},
    "brave":    {"linux": ".config/BraveSoftware/Brave-Browser",
                 "darwin": "Library/Application Support/BraveSoftware/Brave-Browser",
                 "windows": "AppData/Local/BraveSoftware/Brave-Browser/User Data"},
    "opera":    {"linux": ".config/opera", "darwin": "Library/Application Support/com.operasoftware.Opera",
                 "windows": "AppData/Roaming/Opera Software/Opera Stable"},
    "vivaldi":  {"linux": ".config/vivaldi", "darwin": "Library/Application Support/Vivaldi",
                 "windows": "AppData/Local/Vivaldi/User Data"},
    "safari":   {"darwin": "Library/Safari"},
}

_OS_KEY = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}


def detect_browsers(home=None):
    """Return the set of installed browsers, by profile-directory EXISTENCE only.
    Never reads any file inside those directories."""
    home = home or os.path.expanduser("~")
    osk = _OS_KEY.get(platform.system())
    found = set()
    if not osk:
        return found
    for name, paths in BROWSERS.items():
        rel = paths.get(osk)
        if rel and os.path.isdir(os.path.join(home, rel)):
            found.add(name)
    return found
```

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k detect -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): BROWSERS + detect_browsers (presence only)"
```

---

## Task 6: `downloads_dir` + `export_instructions`

**Files:**
- Modify: `bitwarden_vault_cleanup.py`
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_downloads_dir_prefers_existing(tmp_path, monkeypatch):
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(bvc.os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    assert bvc.downloads_dir().endswith("Downloads")


def test_export_instructions_known_browser_mentions_export():
    text = bvc.export_instructions("chrome")
    assert "export" in text.lower()
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k "downloads_dir or export_instructions" -v`
Expected: FAIL — attributes missing.

- [ ] **Step 3: Implement**

```python
_EXPORT_STEPS = {
    "chrome":  "Chrome: Settings -> Autofill and passwords -> Google Password Manager -> "
               "Settings -> Export passwords. Save the CSV to your Downloads folder.",
    "edge":    "Edge: Settings -> Profiles -> Passwords -> (...) -> Export passwords. "
               "Save the CSV to your Downloads folder.",
    "brave":   "Brave: Settings -> Passwords and autofill -> Password Manager -> Settings -> "
               "Export passwords. Save the CSV to your Downloads folder.",
    "opera":   "Opera: Settings -> Privacy & security -> Passwords -> (...) -> Export passwords. "
               "Save the CSV to your Downloads folder.",
    "vivaldi": "Vivaldi: Settings -> Passwords -> Export passwords. Save the CSV to Downloads.",
    "firefox": "Firefox: menu -> Passwords -> (...) menu (top-right) -> Export Logins. "
               "Save the CSV to your Downloads folder.",
    "safari":  "Safari/macOS: open the Passwords app -> File -> Export Passwords. "
               "Save the CSV to your Downloads folder. (No automatic detection on Safari.)",
}


def downloads_dir():
    """OS-aware Downloads directory; falls back to CWD if it does not exist."""
    if platform.system() == "Windows":
        cand = os.path.join(os.path.expanduser("~"), "Downloads")
    else:
        cand = os.path.join(os.path.expanduser("~"), "Downloads")
    return cand if os.path.isdir(cand) else os.getcwd()


def export_instructions(browser):
    return _EXPORT_STEPS.get(browser, f"{browser}: use its built-in 'Export passwords' to CSV.")
```

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k "downloads_dir or export_instructions" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): downloads_dir + export_instructions"
```

---

## Task 7: `collect_source` — guided wait-for-export (injectable clock/watcher)

**Files:**
- Modify: `bitwarden_vault_cleanup.py`
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing tests** (no real waiting; inject a watcher that returns a path immediately, and one that times out)

Append:

```python
def test_collect_source_returns_watched_file():
    def fake_watch(kinds, since):
        return os.path.join(FX, "chromium.csv")     # appears immediately
    path = bvc.collect_source("chrome", expected_kinds={"chromium_csv"},
                              watch=fake_watch, ask=lambda prompt: "", now=lambda: 0.0)
    assert path.endswith("chromium.csv")


def test_collect_source_timeout_then_skip_returns_none():
    def fake_watch(kinds, since):
        return None                                  # never appears
    # ask() returns "" (skip) when prompted after timeout
    path = bvc.collect_source("chrome", expected_kinds={"chromium_csv"},
                              watch=fake_watch, ask=lambda prompt: "", now=lambda: 999.0,
                              timeout=0.0)
    assert path is None


def test_collect_source_accepts_pasted_path():
    def fake_watch(kinds, since):
        return None
    pasted = os.path.join(FX, "firefox.csv")
    path = bvc.collect_source("firefox", expected_kinds={"firefox_csv"},
                              watch=fake_watch, ask=lambda prompt: pasted, now=lambda: 999.0,
                              timeout=0.0)
    assert path == pasted
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k collect_source -v`
Expected: FAIL — no attribute `collect_source`.

- [ ] **Step 3: Implement `collect_source`**

```python
def collect_source(browser, expected_kinds, watch, ask, now, timeout=180.0, poll=1.0, info=print):
    """Guide the user to export `browser`, then return a path to the produced file (or None).

    Dependency-injected for tests: `watch(kinds, since) -> path|None` polls the filesystem,
    `ask(prompt) -> str` reads a line, `now() -> float` is the clock, `info(msg)` prints.
    In production these are real (a Downloads watcher, ui.ask, time.time(), ui.info)."""
    info("\n" + export_instructions(browser))
    start = now()
    while now() - start < timeout:
        hit = watch(expected_kinds, start)
        if hit:
            info(f"  detected export: {hit}")
            return hit
        if poll:
            _sleep(poll)
    # timed out: let the user paste a path or skip
    resp = ask(f"  No {browser} export detected. Paste a path, or press Enter to skip: ").strip()
    if resp and os.path.isfile(resp):
        return resp
    return None
```

Add a tiny indirection so tests never really sleep — add near the top helpers:

```python
def _sleep(seconds):
    time.sleep(seconds)
```

(Tests pass `now` such that the loop exits immediately, so `_sleep` is not hit; production uses it.)

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k collect_source -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): collect_source guided wait-for-export"
```

---

## Task 8: `aggregate_sources` — orchestrate detect/scan/convert into one item list

**Files:**
- Modify: `bitwarden_vault_cleanup.py`
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing test** (fully injected; no prompts, no real browsers)

Append:

```python
def test_aggregate_sources_merges_found_files():
    found = [
        (os.path.join(FX, "bitwarden.json"), "bitwarden_json"),
        (os.path.join(FX, "chromium.csv"), "chromium_csv"),
    ]
    # confirm=lambda *_: True approves aggregation; no browsers need guided export
    items, sources = bvc.aggregate_sources(found=found, installed=set(),
                                           confirm=lambda *_: True,
                                           collect=lambda *a, **k: None)
    # bitwarden has 1 item; chromium has 2 -> 3 total pre-dedup
    assert len(items) == 3
    assert sources["bitwarden_json"] == 1 and sources["chromium_csv"] == 2
    # every item carries an id (required by deduplicate)
    assert all(it.get("id") for it in items)


def test_aggregate_sources_declined_returns_empty():
    items, sources = bvc.aggregate_sources(found=[], installed=set(),
                                           confirm=lambda *_: False, collect=lambda *a, **k: None)
    assert items == [] and sources == {}
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k aggregate_sources -v`
Expected: FAIL — no attribute `aggregate_sources`.

- [ ] **Step 3: Implement `aggregate_sources`**

```python
def _items_from(path, kind):
    if kind == "bitwarden_json":
        data = load_vault(path)
        return data.get("items", []) if isinstance(data, dict) else []
    return csv_to_items(path, kind)


def aggregate_sources(found, installed, confirm, collect):
    """Detect-and-offer orchestrator. Returns (merged_items, per_source_counts).

    `found`     : [(path, kind)] already on disk (from scan_for_exports)
    `installed` : set of browser names (from detect_browsers) to offer guided export for
    `confirm(found, installed) -> bool` : the aggregate? prompt
    `collect(browser, expected_kinds) -> path|None` : guided wait-for-export for a browser
    All side-effecting deps are injected so the orchestrator is unit-testable."""
    if not confirm(found, installed):
        return [], {}

    paths = list(found)
    # offer guided export for installed browsers whose kind isn't already present
    present_kinds = {k for _, k in found}
    browser_kind = {"chrome": "chromium_csv", "edge": "chromium_csv", "brave": "chromium_csv",
                    "opera": "chromium_csv", "vivaldi": "chromium_csv",
                    "firefox": "firefox_csv", "safari": "safari_csv"}
    for b in sorted(installed):
        kind = browser_kind.get(b)
        if not kind:
            continue
        hit = collect(b, {kind})
        if hit:
            paths.append((hit, classify_export(hit) or kind))

    items, counts = [], {}
    for path, kind in paths:
        got = _items_from(path, kind)
        items.extend(got)
        counts[kind] = counts.get(kind, 0) + len(got)
    return items, counts
```

- [ ] **Step 4: Run, expect PASS**

Run: `python -m pytest tests/test_aggregate.py -k aggregate_sources -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): aggregate_sources orchestrator"
```

---

## Task 9: End-to-end — aggregated items flow through dedup unchanged

**Files:**
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing test** (proves the spec's core promise: union + dedup)

Append:

```python
def test_end_to_end_aggregate_then_dedup_collapses_overlap():
    # bitwarden.json has example.com/alice/pw1; chromium.csv ALSO has example.com/alice/pw1
    # (exact dup -> collapses) plus NoUrlRow/bob (browser-only -> preserved via passthrough)
    found = [
        (os.path.join(FX, "bitwarden.json"), "bitwarden_json"),
        (os.path.join(FX, "chromium.csv"), "chromium_csv"),
    ]
    items, _ = bvc.aggregate_sources(found=found, installed=set(),
                                     confirm=lambda *_: True, collect=lambda *a, **k: None)
    # split exactly like main(): non-login passthrough, passkey, dedup inputs
    non_login = [e for e in items if 'login' not in e]
    passkey = [e for e in items if 'login' in e and bvc.has_passkey(e)]
    dedup_in = [e for e in items if 'login' in e and not bvc.has_passkey(e)]
    no_url = [e for e in dedup_in if not e['login'].get('uris')]
    with_url = [e for e in dedup_in if e['login'].get('uris')]
    cleaned, _skipped = bvc.clean_entries(with_url, [])
    reused = bvc.index_passwords(cleaned)
    deduped, merged, removed = bvc.deduplicate(cleaned, reused)
    final_ids = {e['id'] for e in deduped + non_login + passkey + no_url}
    # the two identical example.com/alice/pw1 entries collapse to one; bob (no url) preserved
    names = sorted(e['name'] for e in deduped)
    assert "example.com" in names
    assert removed == 1                       # the exact duplicate was removed
    assert any(e['login'].get('username') == 'bob' for e in no_url)   # browser-only preserved
```

- [ ] **Step 2: Run, expect PASS** (no new production code — this validates the integration)

Run: `python -m pytest tests/test_aggregate.py -k end_to_end -v`
Expected: PASS. If it fails, the bug is in an earlier task's mapping — fix there, not here.

- [ ] **Step 3: Commit**

```bash
git add tests/test_aggregate.py
git commit -m "test(aggregate): end-to-end union+dedup"
```

---

## Task 10: Wire the front-end into `main()` + a real Downloads watcher

**Files:**
- Modify: `bitwarden_vault_cleanup.py` (`main()`, add `_real_watch` + `--aggregate` arg)

- [ ] **Step 1: Add the `--aggregate` flag** in `parse_args_or_prompt`'s parser block

```python
    parser.add_argument('--aggregate', action='store_true',
                        help='Detect installed browsers and aggregate their exports + the vault')
```

- [ ] **Step 2: Add a real Downloads watcher** (used only in production; the unit tests inject fakes)

```python
def _real_watch(expected_kinds, since):
    """Return the path of the newest CSV in Downloads/CWD created after `since` whose sniffed
    kind is in expected_kinds, else None."""
    for d in (downloads_dir(), os.getcwd()):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.lower().endswith('.csv'):
                continue
            p = os.path.join(d, name)
            try:
                if os.path.getmtime(p) < since:
                    continue
            except OSError:
                continue
            if classify_export(p) in expected_kinds:
                return os.path.realpath(p)
    return None
```

- [ ] **Step 3: Call the front-end at the top of `main()`**, before the classic vault load

Insert at the start of `main()` (after `args = parse_args_or_prompt()`), guarded so the classic
path is untouched when not aggregating and stdin is non-interactive:

```python
    aggregated_items = []
    agg_counts = {}
    if args.aggregate or (sys.stdin.isatty() and not args.personal_vault):
        installed = detect_browsers()
        found = scan_for_exports([downloads_dir(), os.getcwd()])
        if (args.aggregate or found or installed) and sys.stdin.isatty():
            def _confirm(found, installed):
                names = ", ".join(sorted(installed)) or "none"
                print(f"\nDetected installed browsers: {names}")
                print(f"Found {len(found)} existing export file(s) in Downloads/CWD.")
                return input("Aggregate browser exports + a Bitwarden export into one "
                             "cleaned vault? [y/N]: ").strip().lower() == "y"

            def _collect(browser, kinds):
                return collect_source(browser, expected_kinds=kinds, watch=_real_watch,
                                      ask=input, now=time.time)

            aggregated_items, agg_counts = aggregate_sources(found, installed, _confirm, _collect)
            if agg_counts:
                print("  aggregated:", ", ".join(f"{k}={v}" for k, v in agg_counts.items()))
            # if a Bitwarden JSON was among the sources, also use it as personal_vault base
            if not args.personal_vault:
                for path, kind in found:
                    if kind == "bitwarden_json":
                        args.personal_vault = path
                        break
```

Then, where `personal_items` is built, fold in the aggregated browser items:

```python
    personal_items = personal_data.get('items', [])
    # browser-sourced items (already converted to bw items) join the dedup population;
    # a Bitwarden JSON among the sources is already loaded as personal_data, so skip its items here
    personal_items = personal_items + [it for it in aggregated_items if it.get("_kind") != "bitwarden_json"]
```

Note: `aggregate_sources` does NOT tag items with `_kind`; to avoid double-counting the
Bitwarden JSON (loaded once as `personal_data` AND once in `aggregated_items`), exclude
`bitwarden_json` items at aggregation time — adjust `aggregate_sources` to skip re-loading a
path already chosen as `personal_vault`. Implement the simplest correct version:

```python
    # In main(), after choosing personal_vault, drop any aggregated items that came from it:
    chosen = os.path.realpath(args.personal_vault) if args.personal_vault else None
    personal_items = personal_data.get('items', [])
    extra = [it for it in aggregated_items]   # browser CSV items only; bitwarden handled below
    # aggregate_sources already returns bitwarden items too; de-dup the source file:
    # simplest: rebuild extra from CSV sources only
```

To keep this unambiguous, **change `aggregate_sources` to return browser-only items** plus the
counts (the Bitwarden JSON is loaded by the classic path). Update Task 8's implementation: when
iterating `paths`, skip `kind == "bitwarden_json"` for the item list but still count it; main()
loads the Bitwarden JSON itself. Re-run Task 8 tests after this change and update
`test_aggregate_sources_merges_found_files` to expect `len(items) == 2` (chromium only) with
`sources` still reporting `bitwarden_json: 1`.

- [ ] **Step 4: Update Task 8 code + test for browser-only items**

In `aggregate_sources`, change the accumulation loop:

```python
    items, counts = [], {}
    for path, kind in paths:
        got = _items_from(path, kind)
        counts[kind] = counts.get(kind, 0) + len(got)
        if kind != "bitwarden_json":          # bitwarden JSON is loaded by the classic path
            items.extend(got)
    return items, counts
```

Update `test_aggregate_sources_merges_found_files`:

```python
    assert len(items) == 2                     # chromium only; bitwarden loaded by main()
    assert sources["bitwarden_json"] == 1 and sources["chromium_csv"] == 2
```

And update the end-to-end test (Task 9) to load the Bitwarden items via `load_vault` + the
browser items via `aggregate_sources`, mirroring `main()`:

```python
    bw_items = bvc.load_vault(os.path.join(FX, "bitwarden.json"))["items"]
    browser_items, _ = bvc.aggregate_sources(
        found=[(os.path.join(FX, "chromium.csv"), "chromium_csv")],
        installed=set(), confirm=lambda *_: True, collect=lambda *a, **k: None)
    items = bw_items + browser_items
```

- [ ] **Step 5: Full suite + a manual smoke run**

Run: `python -m pytest -v`
Expected: PASS (all aggregation tests + the import smoke test).

Manual smoke (non-interactive must NOT hang or change classic behavior):
Run: `printf '' | python bitwarden_vault_cleanup.py tests/fixtures/bitwarden.json --dry-run`
Expected: classic dry-run summary, no aggregation prompt (stdin not a TTY), exit 0.

- [ ] **Step 6: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): wire front-end into main() + Downloads watcher"
```

---

## Task 11: Docs — README section + COMPATIBILITY note

**Files:**
- Modify: `README.md`, `COMPATIBILITY.md`

- [ ] **Step 1: Add a README "Aggregate from browsers" section** (terse, no emoji)

Add after the "What This Script Does" section:

```markdown
## Aggregate passwords from your browsers (optional)

Run with `--aggregate` (or just run it with no file argument in a terminal). The script:
- detects which browsers are installed — by checking only whether their profile folder exists;
  it never opens, reads, or decrypts any browser password store,
- offers to aggregate them plus your Bitwarden export into one cleaned vault,
- walks you through each browser's own "Export passwords" step and picks up the CSV from your
  Downloads folder,
- merges everything and deduplicates it into one import-ready JSON.

Your browser passwords are only ever read from files YOU export. Nothing is read from the
encrypted browser stores. See SECURITY note in COMPATIBILITY.md.
```

Also refresh the successor/positioning wording to the three-branch family (same dedup core, three
automation levels): **Manual** = this tool (file in → cleaned file out, you export/import by hand);
**CLI** = [bw-vault-tools](https://github.com/no84by/bw-vault-tools) `bw-dedup` (drives the `bw`
CLI, in-place delta dedup, no purge); **Auto** = bw-vault-tools `bw-sync` (autonomous reversible
two-way sync). Replace the single "advanced sibling" line with this triad framing.

- [ ] **Step 2: Add the security note to `COMPATIBILITY.md`**

```markdown
## Browser aggregation — what it does and does not touch

The optional `--aggregate` mode detects installed browsers by directory existence only and
ingests password CSVs that YOU export via each browser's built-in exporter. It never reads,
copies, or decrypts `Login Data`, `key4.db`, the macOS Keychain, or any other credential store.
Supported export CSVs: Chromium (Chrome/Edge/Brave/Opera/Vivaldi), Firefox, Safari.
```

- [ ] **Step 3: Commit**

```bash
git add README.md COMPATIBILITY.md
git commit -m "docs: aggregate-from-browsers section + security note"
```

---

## Task 12: Optional `rich` UI layer (graceful stdlib fallback) + route front-end through it

**Files:**
- Modify: `bitwarden_vault_cleanup.py` (add UI classes + `get_ui`; route the `main()` aggregation block, confirm/collect closures, and per-source summary through `ui`)
- Modify: `tests/test_aggregate.py`

- [ ] **Step 1: Write the failing tests** (plain UI is deterministic; factory is import-driven)

```python
def test_get_ui_returns_an_object_with_the_interface():
    ui = bvc.get_ui()
    for m in ("heading", "info", "warn", "confirm", "ask", "table", "rule"):
        assert callable(getattr(ui, m))


def test_plain_ui_confirm_yes_no(monkeypatch, capsys):
    ui = bvc._PlainUI()
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert ui.confirm("ok?") is True
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert ui.confirm("ok?") is False


def test_plain_ui_table_renders_rows(capsys):
    ui = bvc._PlainUI()
    ui.table("Sources", [["bitwarden", "1"], ["chromium", "2"]])
    out = capsys.readouterr().out
    assert "bitwarden" in out and "chromium" in out
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python -m pytest tests/test_aggregate.py -k "ui" -v`
Expected: FAIL — no attribute `get_ui` / `_PlainUI`.

- [ ] **Step 3: Implement the UI layer**

```python
class _PlainUI:
    """Stdlib-only renderer. The always-available baseline."""
    def heading(self, text):
        print("\n" + text)
        print("-" * len(text))
    def info(self, text):
        print(text)
    def warn(self, text):
        print("[!] " + text, file=sys.stderr)
    def rule(self):
        print("-" * 60)
    def ask(self, prompt):
        return input(prompt)
    def confirm(self, prompt):
        return input(prompt.rstrip() + " [y/N]: ").strip().lower() == "y"
    def table(self, title, rows):
        if title:
            print("\n" + title + ":")
        for row in rows:
            print("   " + "  ".join(str(c) for c in row))


class _RichUI:
    """Prettier renderer used only when `rich` is installed. Same interface as _PlainUI."""
    def __init__(self, rich):
        from rich.console import Console
        self._c = Console()
        self._rich = rich
    def heading(self, text):
        self._c.rule(f"[bold]{text}")
    def info(self, text):
        self._c.print(text)
    def warn(self, text):
        self._c.print(f"[yellow]\\[!] {text}")
    def rule(self):
        self._c.rule()
    def ask(self, prompt):
        return self._c.input(prompt)
    def confirm(self, prompt):
        from rich.prompt import Confirm
        return Confirm.ask(prompt, default=False)
    def table(self, title, rows):
        from rich.table import Table
        t = Table(title=title)
        for i in range(max((len(r) for r in rows), default=0)):
            t.add_column(str(i))
        for r in rows:
            t.add_row(*(str(c) for c in r))
        self._c.print(t)


def get_ui():
    """Return a _RichUI if `rich` is importable, else the stdlib _PlainUI. rich is optional and
    is never installed by this tool."""
    try:
        import rich
        return _RichUI(rich)
    except Exception:
        return _PlainUI()
```

- [ ] **Step 4: Route the front-end through `ui`** — update the `main()` aggregation block (Task 10 Step 3)

Build `ui = get_ui()` at the top of the aggregation block and replace its bare `print`/`input`
with `ui` calls; pass `ui.info` into `collect_source`:

```python
    aggregated_items, agg_counts = [], {}
    ui = get_ui()
    if args.aggregate or (sys.stdin.isatty() and not args.personal_vault):
        installed = detect_browsers()
        found = scan_for_exports([downloads_dir(), os.getcwd()])
        if (args.aggregate or found or installed) and sys.stdin.isatty():
            def _confirm(found, installed):
                ui.heading("Aggregate passwords from your browsers")
                ui.table("Detected installed browsers",
                         [[b] for b in sorted(installed)] or [["(none)"]])
                ui.table("Existing export files found",
                         [[os.path.basename(p), k] for p, k in found] or [["(none)", ""]])
                return ui.confirm("Aggregate browser exports + a Bitwarden export into one "
                                  "cleaned vault?")

            def _collect(browser, kinds):
                return collect_source(browser, expected_kinds=kinds, watch=_real_watch,
                                      ask=ui.ask, now=time.time, info=ui.info)

            aggregated_items, agg_counts = aggregate_sources(found, installed, _confirm, _collect)
            if agg_counts:
                ui.table("Aggregated", [[k, v] for k, v in agg_counts.items()])
            if not args.personal_vault:
                for path, kind in found:
                    if kind == "bitwarden_json":
                        args.personal_vault = path
                        break
```

- [ ] **Step 5: Full suite + both render paths**

Run: `python -m pytest -v`
Expected: PASS (plain UI path is what tests exercise).

Optional pretty check (only if you want to see rich): `pip install rich` into a throwaway venv,
run the tool with `--aggregate` against the fixtures dir; confirm tables render and that
`pip uninstall rich` still leaves the tool fully working (plain fallback).

- [ ] **Step 6: Commit**

```bash
git add bitwarden_vault_cleanup.py tests/test_aggregate.py
git commit -m "feat(aggregate): optional rich UI layer with stdlib fallback"
```

---

## Self-Review

**Spec coverage:**
- Presence-only detection (Cornerstone 1) → Task 5 (`detect_browsers` reads dir existence; test asserts it) + README/COMPAT wording. ✓
- Ingest only user-produced exports (Cornerstone 2) → Tasks 3/4/7 operate on files; no store access anywhere. ✓
- Reuse dedup verbatim (Cornerstone 3) → Task 9 end-to-end feeds items through unchanged `clean_entries`/`deduplicate`; no new conflict policy. ✓
- v2.1 guarantees on merged result (Cornerstone 4) → Task 10 routes everything through the existing `main()` path (validate_vault on the Bitwarden JSON, 0600 write, no plaintext print). ✓
- `id` requirement → Task 4 assigns `uuid4`; tests assert it; Task 8/9 assert all items carry id. ✓
- OS-aware Downloads → Task 6 `downloads_dir`. ✓
- Guided wait-for-export with timeout + paste-path + skip + non-TTY disables loop → Task 7 (`collect_source`) + Task 10 (TTY guard). ✓
- Header-signature classification, skip-unknown → Task 2 (`random.csv` → None). ✓
- Per-source counts in summary → Task 8 returns counts; Task 10 prints them. ✓
- Formats: Bitwarden JSON + Chromium/Firefox/Safari CSV → Tasks 2/4 cover all four. ✓
- Terminal UI: optional `rich`, stdlib fallback, one `ui` abstraction → Task 12 (`get_ui`/`_PlainUI`/`_RichUI`); front-end routed through `ui`; `rich` never required/installed. Task 10 wires the front-end with plain print/input first; Task 12 swaps those to `ui` calls (build-then-beautify). ✓

**Placeholder scan:** Task 10 originally described an ambiguous `_kind`/double-count approach, then RESOLVES it explicitly in Steps 3–4 (aggregate_sources returns browser-only items; Bitwarden JSON loaded by the classic path; tests updated). No "TBD"/"add error handling" placeholders remain.

**Type consistency:** `classify_export(path)->str|None`, `scan_for_exports(dirs)->[(path,kind)]`,
`csv_to_items(path,kind)->[item]`, `detect_browsers(home=None)->set`, `downloads_dir()->str`,
`export_instructions(browser)->str`, `collect_source(browser, expected_kinds, watch, ask, now, timeout, poll)->path|None`,
`aggregate_sources(found, installed, confirm, collect)->(items, counts)` — names/signatures
consistent across tasks and the `main()` wiring. Item dict shape matches the v2.1 reader
(`type`, `name`, `notes`, `login.{uris,username,password,totp,fido2Credentials}`, `id`).

**Two corrections folded in during review (applied above):**
1. `aggregate_sources` returns **browser-only** items (excludes `bitwarden_json` from the item
   list but still counts it) so the Bitwarden JSON loaded by the classic `main()` path is not
   double-counted (Task 8 Step 3 + Task 10 Step 4).
2. `downloads_dir()` branch is identical on both OS arms today (both `~/Downloads`); kept the
   branch for clarity/future Windows divergence — harmless, not a placeholder.

---

## Execution note

Builds entirely within `bitwarden-vault-cleanup` on `feat/aggregate-sources`. No new runtime
dependencies (stdlib only); `pytest` is dev-only and never shipped to users who download the
single script. After Task 11, finish via `superpowers:finishing-a-development-branch`.
