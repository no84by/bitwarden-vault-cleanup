#!/usr/bin/env python3
# bitwarden_vault_cleanup.py

"""
Bitwarden Vault Cleanup Script (v2.1)
─────────────────────────────────────

This script helps clean, normalize, and deduplicate Bitwarden vault exports.

v2.1 (2026-05) — safety + robustness hardening:
  - Refuses encrypted exports / non-Bitwarden JSON / missing 'items'; warns on a
    zero-item file, so it can never write an empty vault you then re-import.
  - Tolerates null/empty URIs (`{"uri": null}`) that previously crashed the whole run.
  - Output file written with mode 0600 (it contains plaintext passwords).
  - Reused-password values are no longer printed (only counts, to stderr).
  - Clean exit codes; handles non-interactive stdin (no EOFError traceback).
  - Wrapped execution in main(); internal cleanups (dead code, typos).

v2.0.1 (2026-05) — fix (issue #1): login items without a URI (and any item the
  cleaner cannot deduplicate) are now preserved unchanged in the output instead of
  being silently dropped.

v2.0 (2026-05) — compatibility update for the Bitwarden 2026.x export schema:
  - SSH-key items (type 5) are now labelled, counted, and passed through untouched.
  - Passkey-bearing logins (login.fido2Credentials) are detected, EXCLUDED from
    deduplication (so a merge can never drop a passkey), and reported with a loud
    warning — because `bw export` does not faithfully round-trip passkeys
    (github.com/bitwarden/clients#6925) and a purge+reimport can lose them.
  See COMPATIBILITY.md. For in-place delta apply (no purge+reimport) and two-way
  sync, see the successor project: github.com/no84by/bw-vault-tools

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE:
  python bitwarden_vault_cleanup.py <personal_vault.json> [organization_vault.json] [--dry-run | --help]

EXAMPLES:
  python bitwarden_vault_cleanup.py vault_export.json
  python bitwarden_vault_cleanup.py vault_export.json vault_org_export.json
  python bitwarden_vault_cleanup.py vault_export.json vault_org_export.json --dry-run

If you forget to provide required arguments, the script will guide you interactively.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HELPFUL LINKS:
  Export personal vault: `https://vault.bitwarden.com/#/tools/export`
  Export organizational vault: `https://vault.bitwarden.com/#/organizations/<ORG-ID>/settings/tools/export`
  Import vault: `https://vault.bitwarden.com/#/tools/import`
  Purge vault:  `https://vault.bitwarden.com/#/settings/account`

Tip: When exporting, choose the “JSON” format (NOT “JSON (Encrypted)”)
     Keep track of the filenames and folder where you save the exports.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIVACY & SECURITY:
  - This script runs 100% locally on your machine
  - It does not transmit or save any data externally
  - Original vault files remain untouched
  - Cleaned result is saved as a new JSON file

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import json
import re
import argparse
import platform
import time
import csv
import uuid
if platform.system() == "Windows":
    os.system("chcp 65001 >nul")
    sys.stdout.reconfigure(encoding='utf-8')

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path



TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

TYPE_LABELS = {
    "1": "Logins",
    "2": "Secure Notes",
    "3": "Cards",
    "4": "Identities",
    "5": "SSH Keys",
    "unknown": "Unknown Type",
}

def parse_args_or_prompt():
    parser = argparse.ArgumentParser(
        description="Clean and deduplicate Bitwarden vault exports (JSON format).",
        add_help=False
    )

    parser.add_argument('personal_vault', nargs='?', help='Path to personal Bitwarden vault export (JSON)')
    parser.add_argument('org_vault', nargs='?', help='Optional path to organization Bitwarden vault export (JSON)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving output')
    parser.add_argument('--aggregate', action='store_true',
                        help='Detect installed browsers and aggregate their exports + the vault')
    parser.add_argument('--help', action='store_true', help='Show step-by-step usage help')

    args = parser.parse_args()

    if args.help:
        print_detailed_help()
        sys.exit(0)

    if not args.personal_vault and not args.aggregate:
        if not sys.stdin.isatty():
            sys.exit("[ERROR] No personal vault path given and stdin is not interactive. "
                     "Pass the export path as an argument.")
        print_help_header()
        print("\n[WARNING] Missing required argument: personal_vault")
        try:
            args.personal_vault = input("-> Personal vault file name (and path if not in the same folder): ").strip()
        except EOFError:
            sys.exit("\n[ERROR] No input received. Pass the export path as an argument.")

    if not args.org_vault and sys.stdin.isatty():
        response = input("-> Optional org vault file name (press Enter to skip): ").strip()
        args.org_vault = response if response else None

    return args

def print_help_header():
    print("""
Hello there, you seem to have misunderstood the usage of this script. We need you to provide some arguments. Here is how you can do that:

 EXPORT PERSONAL VAULT:
   - Go to: https://vault.bitwarden.com/#/tools/export
   - Choose: “JSON” format (NOT “JSON (Encrypted)”)

 EXPORT ORGANIZATIONAL VAULT (IF APPLICABLE):
   - Visit: https://vault.bitwarden.com/#/organizations/<ORG-ID>/settings/tools/export
   - Choose: “JSON” format

 PLACE FILES IN THE SAME FOLDER WITH THIS SCRIPT:
   - Note the file names of the export files - something like <filename>.json
   - Type or paste (right click) those file names here, one at a time

""")

def print_detailed_help():
    print("""

This script helps clean and deduplicate Bitwarden JSON vault exports.
It works with a personal vault and optionally an organizational vault.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT IT DOES:
• Identifies and removes fully duplicate entries
• Merges complementary logins (e.g., app + website)
• Flags reused passwords as potentially compromised
• Assigns folders if the folder name matches part of the username
• Removes personal entries already stored in the organizational vault
• Leaves ambiguous or unclear duplicates untouched for safety

The output is a cleaned Bitwarden-compatible JSON file, safe for re-import.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE:

  python bitwarden_vault_cleanup.py <personal_vault.json> [organization_vault.json] [--dry-run | --help]

NOTES:

• When exporting your vault, choose: “JSON” (NOT “JSON (Encrypted)”)
• Place the export file(s) and this script in the same folder before running
• Use --dry-run to preview actions without writing any files
• Folder assignment only works if the folder already exists in Bitwarden

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST-CLEANUP RECOMMENDATIONS:

1. Purge your existing vault for a fresh start: 
   https://vault.bitwarden.com/#/settings/account -> “Purge Vault”

2. Import your cleaned JSON:
   https://vault.bitwarden.com/#/tools/import -> Format: JSON

3. If you’re unhappy with the results:
   - Re-import your original vault export
   - You can safely repeat this cleanup anytime

4. Once you're satisfied:
   - DELETE ALL `.json` FILES from your computer!
   - Exported vaults contain passwords in plain text and pose a serious security risk

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIVACY & DISCLAIMER:

• This script runs 100% locally
• It does NOT upload, sync, log, or transmit anything
• Your original files are untouched — the cleaned file is saved separately
• This script is provided AS IS, with NO WARRANTY and NO SUPPORT

Always back up your vault before making changes.

""")
def load_vault(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"\n[ERROR] File not found: '{file_path}'")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"\n[ERROR] File is not valid JSON: '{file_path}'")
        sys.exit(1)

def classify_export(path):
    """Sniff a file's export kind by content (not filename). Returns one of
    'bitwarden_json', 'chromium_csv', 'firefox_csv', 'safari_csv', or None."""
    try:
        with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
            head = f.read(4096)
            if head.lstrip().startswith('{'):
                if '"items"' not in head:
                    head += f.read(1_000_000)     # large folders preamble before items
                return 'bitwarden_json' if '"items"' in head else None
    except OSError:
        return None
    first_line = head.splitlines()[0].lower() if head.splitlines() else ''
    cols = {c.strip().strip('"') for c in first_line.split(',')}
    if {'url', 'username', 'password', 'httprealm'} <= cols:
        return 'firefox_csv'
    if {'title', 'url', 'username', 'password'} <= cols:
        return 'safari_csv'
    if {'name', 'url', 'username', 'password'} <= cols:
        return 'chromium_csv'
    return None

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

# column maps: kind -> (name_col, url_col, user_col, pass_col, note_col, source_label)
_CSV_SCHEMA = {
    "chromium_csv": ("name", "url", "username", "password", "note", "chromium"),
    "firefox_csv": (None, "url", "username", "password", None, "firefox"),
    "safari_csv": ("title", "url", "username", "password", "notes", "safari"),
}


def csv_to_items(path, kind):
    """Map a recognized browser CSV to Bitwarden login items (one per row, fresh uuid id)."""
    name_c, url_c, user_c, pass_c, note_c, source = _CSV_SCHEMA[kind]
    items = []
    with open(path, 'r', encoding='utf-8-sig', errors='replace', newline='') as f:
        reader = csv.DictReader(f)
        # lowercased column name -> original fieldname, built once
        by_lower = {(fn or '').strip().lower(): fn for fn in (reader.fieldnames or [])}

        def get(row, col):
            if not col:
                return ''
            orig = by_lower.get(col)
            return (row.get(orig) or '').strip() if orig else ''
        for row in reader:
            url = get(row, url_c)
            name = get(row, name_c) or normalize_uri(url) or "(imported)"
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

# Which CSV schema each browser's exporter produces.
_BROWSER_CSV_KIND = {"chrome": "chromium_csv", "edge": "chromium_csv", "brave": "chromium_csv",
                     "opera": "chromium_csv", "vivaldi": "chromium_csv",
                     "firefox": "firefox_csv", "safari": "safari_csv"}


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
    """Downloads directory (expanduser resolves USERPROFILE on Windows); falls back to CWD."""
    cand = os.path.join(os.path.expanduser("~"), "Downloads")
    return cand if os.path.isdir(cand) else os.getcwd()


def export_instructions(browser):
    return _EXPORT_STEPS.get(browser, f"{browser}: use its built-in 'Export passwords' to CSV.")


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
            info(f"  detected export: {os.path.basename(hit)}")
            return hit
        if poll:
            time.sleep(poll)
    resp = ask(f"  No {browser} export detected. Paste a path, or press Enter to skip: ").strip()
    if resp and os.path.isfile(resp):
        return resp
    return None


def _real_watch(expected_kinds, since):
    """Return the path of the NEWEST CSV in Downloads/CWD modified after `since` whose sniffed
    kind is in expected_kinds, else None."""
    candidates = []
    for d in (downloads_dir(), os.getcwd()):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.lower().endswith('.csv'):
                continue
            p = os.path.join(d, name)
            try:
                mtime = os.path.getmtime(p)
            except OSError:
                continue
            if mtime < since:
                continue
            if classify_export(p) in expected_kinds:
                candidates.append((mtime, os.path.realpath(p)))
    return max(candidates)[1] if candidates else None


def _items_from(path, kind):
    if kind == "bitwarden_json":
        data = load_vault(path)
        return data.get("items", []) if isinstance(data, dict) else []
    return csv_to_items(path, kind)


def aggregate_sources(found, installed, confirm, collect):
    """Detect-and-offer orchestrator. Returns (browser_items, per_source_counts).

    `found`     : [(path, kind)] already on disk (from scan_for_exports)
    `installed` : set of browser names to offer guided export for
    `confirm(found, installed) -> bool` : the aggregate? prompt
    `collect(browser, expected_kinds) -> path|None` : guided wait-for-export for a browser
    A found Bitwarden JSON is COUNTED but its items are NOT returned (the classic path loads it).
    All side-effecting deps are injected so the orchestrator is unit-testable."""
    if not confirm(found, installed):
        return [], {}

    paths = list(found)
    present_kinds = {k for _, k in found}
    # One file per CSV schema is enough: same-schema browsers (e.g. all Chromium variants) share
    # the column layout and dedup collapses identical rows. Skip a kind we already have a file for.
    for b in sorted(installed):
        kind = _BROWSER_CSV_KIND.get(b)
        if not kind or kind in present_kinds:   # unknown, or we already have a file of this kind
            continue
        hit = collect(b, {kind})
        if hit:
            paths.append((hit, classify_export(hit) or kind))
            present_kinds.add(kind)

    items, counts = [], {}
    for path, kind in paths:
        got = _items_from(path, kind)
        counts[kind] = counts.get(kind, 0) + len(got)
        if kind != "bitwarden_json":            # bitwarden JSON is loaded by the classic path
            items.extend(got)
    return items, counts


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
        self._c.print(f"[yellow]Warning:[/] {text}")
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


def validate_vault(data, file_path):
    """Refuse anything that is not a plaintext Bitwarden JSON export, so we never write a
    lossy 'cleaned' file the user re-imports over a purged vault."""
    if not isinstance(data, dict):
        print(f"\n[ERROR] '{file_path}': expected a JSON object, got {type(data).__name__}. "
              f"Is this a Bitwarden export?")
        sys.exit(1)
    if data.get("encrypted") is True:
        print(f"\n[ERROR] '{file_path}' is an ENCRYPTED export. Re-export choosing the "
              f"“JSON” format (NOT “JSON (Encrypted)”).")
        sys.exit(1)
    if "items" not in data:
        print(f"\n[ERROR] '{file_path}' has no 'items' key. This does not look like a "
              f"Bitwarden vault export.")
        sys.exit(1)
    if not data.get("items"):
        print(f"\n[WARNING] '{file_path}' contains zero items. Continuing, but verify this "
              f"is the file you meant before re-importing.")

def has_passkey(entry):
    """True if a login entry carries one or more passkeys (fido2Credentials).

    `bw export` is known to emit an empty fido2Credentials array for some clients
    (github.com/bitwarden/clients#6925); when it IS populated we must never let the
    dedup step merge such an entry away, or the passkey is lost.
    """
    login = entry.get('login')
    return bool(login and isinstance(login, dict) and login.get('fido2Credentials'))


def normalize_uri(uri):
    if not uri:                       # tolerate {"uri": null} / empty entries (don't crash the run)
        return ''
    if uri.startswith("android://") or uri.startswith("androidapp://"):
        match = re.search(r'@(.+?)(?:/|$)', uri)
        return match.group(1) if match else uri.split("://")[-1]
    uri = re.sub(r'^https?://', '', uri).lower().rstrip('/')
    domain = uri.split('/')[0]
    return domain

def normalize_name(entry):
    if entry['name'] != '--':
        return entry['name']
    uri = entry['login']['uris'][0]['uri']
    if not uri:
        return entry['name']
    if uri.startswith('android'):
        return normalize_uri(uri).split('.')[-1]
    return normalize_uri(uri).split('.')[0]

def flag_reused_passwords(entries, reused_passwords):
    flag = "[VaultCleanup] [!] This password is reused across multiple sites."
    
    for entry in entries:
        if 'login' not in entry:
            continue
        password = entry['login'].get('password')
        if not password or password not in reused_passwords:
            continue

        existing_notes = entry.get('notes', '')
        
        if flag in (existing_notes or ''):
            continue

        if existing_notes:
            entry['notes'] = f"{existing_notes.strip()}\n\n{flag}"
        else:
            entry['notes'] = flag


def assign_folder_id(entry, folders):
    username = entry['login'].get('username')
    if not username:
        return None, None
    for folder in folders:
        if folder['name'] in username:
            return folder['id'], folder['name']
    return None, None

def clean_entries(entries, folders):
    cleaned = []
    skipped = []

    for entry in entries:
        if 'login' not in entry or not entry['login'].get('uris'):
            skipped.append(entry)
            continue

        original_name = entry['name']
        entry['name'] = normalize_name(entry)
        if entry['name'] != original_name:
            print(f"Renamed {original_name} -> {entry['name']} ({entry['id']})")

        if entry.get('folderId') is None:
            folder_id, folder_name = assign_folder_id(entry, folders)
            if folder_id:
                entry['folderId'] = folder_id
                print(f"Assigned folder {folder_name} ({folder_id}) to {entry['name']} ({entry['id']})")

        cleaned.append(entry)

    return cleaned, skipped

def index_passwords(entries):
    pw_to_domains = defaultdict(set)

    for e in entries:
        login_data = e.get('login')
        if not login_data or not isinstance(login_data, dict):
            continue

        pw = login_data.get('password')
        uris = login_data.get('uris')

        if not pw or not isinstance(pw, str):
            continue

        pw = pw.strip()

        if not pw:
            continue

        if uris:
            for u in uris:
                domain = normalize_uri(u['uri'])
                pw_to_domains[pw].add(domain)

    return {pw for pw, domains in pw_to_domains.items() if len(domains) > 1}



def deduplicate(entries, compromised_passwords):
    grouped = defaultdict(list)
    grouped_entry_ids = set()
    final_entries = []
    merged = 0
    removed = 0

    for entry in entries:
        login_data = entry.get('login')
        if not login_data or not isinstance(login_data, dict):
            continue  # Skip entries with no usable login block
        if not login_data.get('uris'):
            continue  # Skip entries with no URIs

        uri_key = normalize_uri(login_data['uris'][0]['uri'])
        username = login_data.get('username')
        password = login_data.get('password', '')

        if not isinstance(password, str):
            password = str(password)
        password = password.strip()

        key = (uri_key, username, password)
        grouped[key].append(entry)
        grouped_entry_ids.add(entry['id'])

    for (uri, username, password), group in grouped.items():
        if len(group) == 1:
            final_entries.append(group[0])
            continue
        print("\n--------------------------------------------\n")
        print(f"Evaluating group:\n {uri}\n  Username: {username}\n  Entries: {len(group)}")

        all_same = all(
            e['login']['password'] == group[0]['login']['password'] and
            e.get('revisionDate') == group[0].get('revisionDate') and
            e.get('creationDate') == group[0].get('creationDate')
            for e in group
        )

        if all_same:
            kept = group[0]
            final_entries.append(kept)
            removed += len(group) - 1
            print(f"-> Exact duplicates. Kept {kept['name']} ({kept['id']})")
            continue

        candidates = sorted(group, key=lambda e: (
            max([h.get('lastUsedDate', '') for h in (e.get('passwordHistory') or [])], default=''),
            e.get('revisionDate', ''),
            e.get('login', {}).get('password') in compromised_passwords,
            e.get('creationDate', ''),
            e['id']
        ))

        best = candidates[-1]

        merged_uris = set(u['uri'] for e in group for u in e['login'].get('uris', []) if u.get('uri'))
        best['login']['uris'] = [{'uri': uri, 'match': None} for uri in sorted(merged_uris)]

        merged_notes = [e['notes'].strip() for e in group if e.get('notes') and e['notes'].strip()]
        merged_notes = list(dict.fromkeys(merged_notes))
        best['notes'] = "\n\n".join(merged_notes) if merged_notes else None

        final_entries.append(best)
        merged += len(group) - 1

        print(f"-> Merged {len(group)} entries into: {best['name']} ({best['id']})")
        print(f"   |__ Total merged URIs: {len(merged_uris)}")
        if best.get('notes'):
            print(f"   |__ Notes retained ({len(best['notes'].splitlines())} lines)")

    ungrouped = [e for e in entries if e['id'] not in grouped_entry_ids]
    if ungrouped:
        print(f"-> {len(ungrouped)} login entries were ungrouped and added to final output.")
        final_entries.extend(ungrouped)

    return final_entries, merged, removed

def print_folder_breakdown(entries, folders):
    folder_map = {f['id']: f['name'] for f in folders}
    folder_counter = defaultdict(int)

    for e in entries:
        if e.get('type') == 1: 
            folder_id = e.get('folderId')
            name = folder_map.get(folder_id, "[no folder]")
            folder_counter[name] += 1

    print("\n  >> Folder breakdown (logins only):")
    for name, count in sorted(folder_counter.items(), key=lambda x: (-x[1], x[0])):
        print(f"     • {name}: {count} entries")


def print_summary(original, final, compromised, merged, removed, org_count, reused_counter, type_counter, skipped, folders, final_entries, passkey_count=0):
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" CLEAN-UP SUMMARY")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Initial personal entries:                            {original}")
    print(f"Organizational entries provided:                     {org_count}")
    print(f"Deduplicated login entries:                          {len(final_entries)}")
    print(f"Entries with potentially compromised passwords:      {len(compromised)}")
    print(f"Duplicate entries merged:                            {merged}")
    print(f"Duplicate entries removed:                           {removed}")
    print(f"Login entries kept as-is (no URI, not deduped):      {skipped}")
    print(f"Passkey logins passed through (NOT deduped):          {passkey_count}")
    print(f"Final kept entries (for import):                     {final}")
    print("")
    print("\n  >> Final vault item type breakdown:")
    for t, count in sorted(type_counter.items()):
        label = TYPE_LABELS.get(t, f"Type {t}")
        print(f"     • {label}: {count} entries")
    print("")
    print_folder_breakdown(final_entries, folders)
    print("")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if passkey_count:
        print("")
        print("  !!  PASSKEY WARNING  !!")
        print(f"  {passkey_count} login entr(y/ies) contain passkeys (login.fido2Credentials).")
        print("  These were passed through UNTOUCHED (never merged) by this script.")
        print("  BUT: the Bitwarden CLI / JSON export does not reliably round-trip")
        print("  passkeys (github.com/bitwarden/clients#6925). If you follow the")
        print("  PURGE + REIMPORT step below with an export that dropped them, you will")
        print("  LOSE those passkeys. Before purging, verify your export actually")
        print("  contains the fido2Credentials, or re-enrol the passkeys afterwards.")
        print("  Safer alternative (in-place, no purge): github.com/no84by/bw-vault-tools")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


    if compromised:
        # Counts only — never print plaintext passwords (a redirected stdout would leak them).
        print(f"\n  >> {len(compromised)} reused password(s) flagged across "
              f"{sum(reused_counter.values())} entr(y/ies). Values withheld for safety.",
              file=sys.stderr)


def get_output_filename(original):
    base = Path(original).stem if original else "aggregated-vault"
    return f"{base}_cleaned_up_{TIMESTAMP}.json"

def _content_fp(entry):
    login = entry.get("login") or {}
    uris = login.get("uris") or []
    uri = normalize_uri(uris[0]["uri"]) if uris and uris[0].get("uri") else None
    pw = login.get("password")
    return (uri, login.get("username"), pw if isinstance(pw, str) else str(pw) if pw is not None else None)


def exclude_org_dupes(personal_entries, org_items):
    """Drop personal entries whose CONTENT (uri+username+password) matches an org item.
    Matches by content fingerprint, not id (ids never match across exports)."""
    org_fps = {_content_fp(o) for o in org_items if "login" in o and (o["login"].get("uris"))}
    kept = []
    for entry in personal_entries:
        if "login" in entry and entry["login"].get("uris") and _content_fp(entry) in org_fps:
            print(f"-> Removed personal entry already in org vault: {entry.get('name')} ({entry['id']})")
        else:
            kept.append(entry)
    return kept


# === Main script execution ===
def write_output(output_file, personal_data):
    """Write the cleaned vault with owner-only (0600) permissions — it holds plaintext
    passwords. Fail loudly (non-zero exit) rather than leave a half-written file."""
    try:
        fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(personal_data, f, indent=2)
    except OSError as exc:
        print(f"\n[ERROR] Could not write '{output_file}': {exc}")
        sys.exit(1)


def main():
    args = parse_args_or_prompt()
    aggregated_items = []
    if args.aggregate:
        ui = get_ui()
        installed = detect_browsers()
        found = scan_for_exports([downloads_dir(), os.getcwd()])

        def _confirm(found, installed):
            if not sys.stdin.isatty():
                ui.info("(non-interactive: browser aggregation skipped)")
                return False
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
        # if a Bitwarden JSON was found and no vault was given, use it as the base
        if not args.personal_vault and sys.stdin.isatty():
            bw_jsons = [p for p, k in found if k == "bitwarden_json"]
            if bw_jsons and ui.confirm(f"Use {os.path.basename(bw_jsons[0])} as the Bitwarden base vault?"):
                args.personal_vault = bw_jsons[0]
                if len(bw_jsons) > 1:
                    ui.warn(f"Multiple Bitwarden exports found; using {os.path.basename(bw_jsons[0])}. "
                            f"Others ignored: {[os.path.basename(p) for p in bw_jsons[1:]]}.")

    if args.personal_vault:
        personal_data = load_vault(args.personal_vault)
        validate_vault(personal_data, args.personal_vault)
    else:
        # only reached when aggregating with no Bitwarden base found -> synthesize empty base
        personal_data = {"encrypted": False, "folders": [], "items": []}
    org_data = load_vault(args.org_vault) if args.org_vault else {}
    if org_data:
        validate_vault(org_data, args.org_vault)

    folders = personal_data.get('folders', [])
    personal_items = personal_data.get('items', []) + aggregated_items
    non_login_items = [e for e in personal_items if 'login' not in e]
    # Passkey-bearing logins are EXCLUDED from dedup (so a merge can never drop a passkey)
    # and passed through untouched. Only non-passkey logins are deduplicated.
    passkey_items = [e for e in personal_items if 'login' in e and has_passkey(e)]
    dedup_login_items = [e for e in personal_items if 'login' in e and not has_passkey(e)]
    org_items = org_data.get('items', []) if org_data else []


    cleaned_personal, skipped_entries = clean_entries(dedup_login_items, folders)
    compromised_passwords = index_passwords(cleaned_personal + org_items)

    print("\n[INFO] Starting vault clean-up...", flush=True)
    time.sleep(1)

    reused_counter = Counter()
    for entry in cleaned_personal + org_items:
        if 'login' in entry:
            pw = entry['login'].get('password')
            if pw and pw in compromised_passwords:
                reused_counter[pw] += 1

    if org_items:
        cleaned_personal = exclude_org_dupes(cleaned_personal, org_items)

    deduped, merged, removed = deduplicate(cleaned_personal, compromised_passwords)
    flag_reused_passwords(deduped, compromised_passwords)

    # Preserve, unchanged, every item the cleaner could not deduplicate:
    #   - non_login_items : items with no login block (notes, cards, identities, SSH keys)
    #   - passkey_items   : passkey-bearing logins (never deduped; see has_passkey)
    #   - skipped_entries : login items without a URI (cannot be grouped) — issue #1
    # Anything not deduplicable must still round-trip to the output, never be dropped.
    passthrough = non_login_items + passkey_items + skipped_entries
    type_counter = Counter(str(e.get('type', 'unknown')) for e in deduped + passthrough)

    print_summary(
        original=len(personal_items),
        final=len(deduped + passthrough),
        compromised=compromised_passwords,
        merged=merged,
        removed=removed,
        org_count=len(org_items),
        reused_counter=reused_counter,
        type_counter=type_counter,
        skipped=len(skipped_entries),
        folders=folders,
        final_entries=deduped,
        passkey_count=len(passkey_items),
    )

    if args.dry_run:
        print("\n[DRY RUN] No file written.\n")
        return

    personal_data['items'] = deduped + passthrough
    output_file = get_output_filename(args.personal_vault)
    write_output(output_file, personal_data)
    print(f"\n[INFO] Cleaned vault written to: {output_file} (mode 0600 — delete it when done).\n")
    if passkey_items:
        print("[WARNING] This vault contains passkeys — read the PASSKEY WARNING above "
              "before you purge + reimport.")


# === Main script execution ===
if __name__ == "__main__":
    main()
