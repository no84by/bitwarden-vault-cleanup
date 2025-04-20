#!/usr/bin/env python3
# bitwarden_vault_cleanup.py

"""
Bitwarden Vault Cleanup Script (v1.9)
─────────────────────────────────────

This script helps clean, normalize, and deduplicate Bitwarden vault exports.

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
if platform.system() == "Windows":
    os.system("chcp 65001 >nul")
    sys.stdout.reconfigure(encoding='utf-8')

from collections import Counter
from datetime import datetime
from pathlib import Path



TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

def clear_terminal():
    os.system('cls' if platform.system() == 'Windows' else 'clear')

def parse_args_or_prompt():
    parser = argparse.ArgumentParser(
        description="Clean and deduplicate Bitwarden vault exports (JSON format).",
        add_help=False
    )

    parser.add_argument('personal_vault', nargs='?', help='Path to personal Bitwarden vault export (JSON)')
    parser.add_argument('org_vault', nargs='?', help='Optional path to organization Bitwarden vault export (JSON)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving output')
    parser.add_argument('--help', action='store_true', help='Show step-by-step usage help')

    args = parser.parse_args()

    if args.help:
        print_detailed_help()
        sys.exit(0)

    if not args.personal_vault:
        print_help_header()
        print("\n[WARNING] Missing required argument: personal_vault")
        args.personal_vault = input("-> Personal vault file name (and path if not in the same folder): ").strip()

    if not args.org_vault:
        response = input("-> Optional org vault file name (press Enter to skip): ").strip()
        args.org_vault = response if response else None

    return args

def print_help_header():
    clear_terminal()
    print("""
Hello there, you seems to misunderstoon the useage of this script... We need you to provide some arguments. Here is how you can do that:

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
    clear_terminal()
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

def normalize_uri(uri):
    if uri.startswith("android://") or uri.startswith("androidapp://"):
        match = re.search(r'@(.+?)/', uri)
        return match.group(1) if match else uri.split("://")[-1]
    uri = re.sub(r'^https?://', '', uri).lower().rstrip('/')
    domain = uri.split('/')[0]
    return domain

def get_normalized_identity(entry):
    if 'login' not in entry or not entry['login'].get('uris'):
        return None
    uri = entry['login']['uris'][0]['uri']
    return normalize_uri(uri)

def normalize_name(entry):
    if entry['name'] != '--':
        return entry['name']
    uri = entry['login']['uris'][0]['uri']
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
    ambiguous = []
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

        merged_uris = set(u['uri'] for e in group for u in e['login'].get('uris', []))
        best['login']['uris'] = [{'uri': uri, 'match': None} for uri in sorted(merged_uris)]

        merged_notes = [e['notes'].strip() for e in group if e.get('notes') and e['notes'].strip()]
        merged_notes = list(dict.fromkeys(merged_notes))

        if merged_notes:
            best['notes'] = "\n\n".join(merged_notes)
        else:
            best['notes'] = None

        if not best.get('notes'):
            for e in reversed(group):
                if e.get('notes'):
                    best['notes'] = e['notes']
                    break

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

    return final_entries, ambiguous, merged, removed

from collections import defaultdict

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


def print_summary(original, final, compromised, ambiguous, merged, removed, org_count, reused_counter, type_counter, skipped, folders, final_entries):
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" CLEAN-UP SUMMARY")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Initial personal entries:                            {original}")
    print(f"Organizational entries provided:                     {org_count}")
    print(f"Total processed entries:                             {len(deduped)}")
    print(f"Entires with potentially compromised passwords:      {len(compromised)}")
    print(f"Duplicate entries merged:                            {merged}")
    print(f"Duplicate entries removed:                           {removed}")
    print(f"Ambiguous entries retained:                          {len(ambiguous)}")
    print(f"Ommited login entries that slipped cleanup:          {skipped}")
    print(f"Final kept entries (for import):                     {final}")
    print("")
    print(f"\n  >> Final vault item type breakdown:")
    type_labels = {
        "1": "Logins",
        "2": "Secure Notes",
        "3": "Cards",
        "4": "Identities",
        "unknown": "Unknown Type"
    }
    for t, count in sorted(type_counter.items()):
        label = type_labels.get(t, f"Type {t}")
        print(f"     • {label}: {count} entries")
    print("")
    print_folder_breakdown(final_entries, folders)
    print("")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


    if ambiguous:
        print("\n  >> Ambiguous Entry Groups:")
        for group in ambiguous:
            uri, username, entries = group
            print(f"  URI: {uri} | Username: {username}")
            for e in entries:
                print(f"    {e['name']} ({e['id']})")

    if compromised:
        print(f"\n[DEBUG] Reused passwords: {len(compromised_passwords)}. Top reused passwords:")
        for pw, count in reused_counter.most_common(15):
            print(f"               • {(pw)}({count})")


def get_output_filename(original):
    base = Path(original).stem
    return f"{base}_cleanned_up_{TIMESTAMP}.json"

def exclude_org_dupes(personal_entries, org_ids):
    kept = []
    for entry in personal_entries:
        if entry['id'] in org_ids:
            print(f"-> Removed personal entry already in org vault: {entry['name']} ({entry['id']})\n")
        else:
            kept.append(entry)
    return kept


# === Main script execution ===
if __name__ == "__main__":
    args = parse_args_or_prompt()
    personal_data = load_vault(args.personal_vault)
    org_data = load_vault(args.org_vault) if args.org_vault else {}

    folders = personal_data.get('folders', [])
    personal_items = personal_data.get('items', [])
    non_login_items = [e for e in personal_items if 'login' not in e]
    org_items = org_data.get('items', []) if org_data else []
    org_ids = {entry['id'] for entry in org_items} if org_items else set()

    cleaned_personal, skipped_entries = clean_entries(personal_items, folders)
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
        cleaned_personal = exclude_org_dupes(cleaned_personal, org_ids)

    deduped, ambiguous, merged, removed = deduplicate(cleaned_personal, compromised_passwords)
    flag_reused_passwords(deduped, compromised_passwords)

    type_counter = Counter(str(e.get('type', 'unknown')) for e in deduped + non_login_items)

print_summary(
    original=len(personal_items),
    final=len(deduped + non_login_items),
    compromised=compromised_passwords,
    ambiguous=ambiguous,
    merged=merged,
    removed=removed,
    org_count=len(org_items),
    reused_counter=reused_counter,
    type_counter=type_counter,
    skipped=len(skipped_entries),
    folders=folders,
    final_entries=deduped 
)


if args.dry_run:
    print("\n[DRY RUN] No file written.\n")
else:
    personal_data['items'] = deduped + non_login_items
    output_file = get_output_filename(args.personal_vault)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(personal_data, f, indent=2)
    print(f"\n[INFO] Cleaned vault written to: {output_file}\n")
