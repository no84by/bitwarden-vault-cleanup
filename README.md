# bitwarden-vault-cleanup
Python script to clean, normalize, and deduplicate Bitwarden vault exports.  Merges related entries, removes duplicates, excludes organization vault items, and outputs an import-ready JSON file —  all while running locally, without storing, transmitting, or collecting any sensitive data.
---

## ❓ Why This Script Exists

Bitwarden is an open-source and secure password manager — but in terms of **vault hygiene**, it does very little beyond storing and retrieving entries (even that a bit inconsistenly anyway).

Bitwarden:
- Does **not detect or clean up duplicate entries**
- Does **not help you merge multiple login variations** for the same service
- Does **not flag reused passwords** (only compromised passwords and part of the paid plans)
- And does **not offer any tools to organize or normalize imported data**

Even if you're using **Bitwarden Premium**, there is **no built-in mechanism** for maintaining a clean, structured vault.

This becomes especially problematic when:
- You import passwords from **multiple browsers** (e.g., Chrome, Firefox, Edge, Opera etc.)
- You’ve used Bitwarden across multiple devices without manually curating your vault
- You manage multiple identities (personal, family, or work accounts)
- You’ve accumulated years of exported/imported data and vault merges

---
## ✅ What This Script Does

- 📦 Processes **Bitwarden JSON (Decrypted)** exports
- 🧠 Identifies and removes **identical entries** and applies a Deduplication algorithm to
- 🔄 Merge multiple related web and mobile app logins (e.g., `com.app` + `www.website`)
- 🗂 Assigns entries to folders based on usernames (if matching folder names already exist in the vault)
- 🏢 Removes entries from the personal vault that also exist in an organization vault (if export provided)
- 🕵️ Flags reused passwords as **potentially compromised** (in the notes field of each entry, visible in Bitwarden)
- 📤 Outputs a clean, import-ready JSON file
- 🔒 **Runs entirely locally** — no cloud services, no external logging

## 🔍 Deduplication Logic

This script uses a **multi-step logic** to deduplicate entries safely and intelligently.

It groups entries by:
- Normalized **URI** (domain only, ignoring http/https, subpaths, and trailing slashes)
- **Username** (entries without usernames are only deduplicated if they have identical passwords)

Once grouped, the script evaluates which entry to keep based on the following field priority:

### 📌 Comparison Fields (in priority order)

1. **lastUsedDate**  
   If the entry contains `passwordHistory`, the script checks which password was used most recently.

2. **revisionDate**  
   The more recently revised entry is preferred — assuming it's more current.

3. **Password uniqueness**  
   - If one password is reused across other entries (a potential compromise), unique passwords are preferred.
   - Reused passwords are still retained if they have the newer revision date.

4. **creationDate**  
   If all other fields are equal, the newest entry by creation timestamp is kept.

5. **Fallback: first entry**  
   If all entries are identical in all relevant fields, the first one (sorted by ID) is kept and the rest are deleted.


### 🧠 Additional Logic:

- **Exact Matches**  
  If multiple entries have the same URI, username, and password (including formatting), all but one are removed immediately without merging.

- **URI Merging**  
  If entries are nearly identical (same credentials) but differ only by URI (e.g., app vs web), their URIs are combined into a single list and merged into the best entry.

- **Ambiguous Cases**  
  If entries have the same `revisionDate` but different passwords and no clear winner, they are **all retained** and listed as "ambiguous" in the summary.

- **Org Vault Preference**  
  If an identical entry (by ID) exists in the organizational vault, the personal version is removed.

- **Folder Assignment**  
  If a folder exists with a name that appears in the username, the entry is assigned to that folder.


This method prioritizes **safety**, **clarity**, and **maintainability** — no assumptions are made without strong signals from your data.

All decision-making is logged visibly in the terminal, and a summary is printed at the end for your review.



## 📋 Prerequisites

- Python 3.7 or newer (https://www.python.org/downloads)
- One or more Bitwarden vault exports in **JSON** format  
  ⚠️ **Do NOT choose “JSON (Encrypted)”**


## 🔐 Privacy & Security

This script was designed with maximum privacy and security in mind:

- It runs **100% locally** on your machine
- It does **not transmit, sync, or upload** your data
- It does **not modify your original export**
- It only writes one new cleaned JSON file

You are in complete control.  
We strongly recommend reading the script before use — it is transparent and self-contained.
---


## 🚀 How to Use




### Step 1️⃣ Export Your Vaults
Export your vault(s) using the official Bitwarden web vault:

- Personal Vault:  
  `https://vault.bitwarden.com/#/tools/export`

- Organization Vault (if applicable, and only with vault admin rights):  
  `https://vault.bitwarden.com/#/organizations/<ORG-ID>/settings/tools/export`

⚠️ Choose the **“JSON”** format — **NOT** “JSON (Encrypted)”



### Step 2️⃣ Save Files Locally
Download both the **personal** and **organisation** vault export files (if applicable). Note the name of the files and where you saved them.



### Step 3️⃣ Place Files with the Script
Put `bitwarden_vault_cleanup.py` and your export file(s) in the **same folder**

As a minimum your folder will cotain:
- `bitwarden_vault_cleanup.py`
- `vault_export.json` (your personal vault export)
- `vault_org_export.json` (optional, your organisation vault export)



### Step 4️⃣ Open Terminal / PowerShell and Navigate to That Folder
Use `cd` command to move to the folder where your script and export files are saved.

(example) 
```powershell
cd "$env:USERPROFILE\Downloads"
```
or
```powershell
cd "$env:USERPROFILE\Desktop"
```



### Step 5️⃣ Run the Script
Basic usage (personal vault only):

```powershell
python bitwarden_vault_cleanup.py vault_export.json
```

With org vault:
```powershell
python bitwarden_vault_cleanup.py vault_export.json vault_org_export.json
```

Dry run (preview only, no file written):
```powershell
python bitwarden_vault_cleanup.py vault_export.json --dry-run
```

Help: 
```powershell
python bitwarden_vault_cleanup.py --help
```



### Step 6️⃣ Review the Output
Console output will display the progress:
- Number of entries processed
- Number of Duplicates removed
- Number of Entries merged
- Number of Ambiguous entries retained
- Number of Compromised passwords detected
- Final vault size after cleanup (count)

The script creates in the same folder a new JSON file named like: `vault_export_cleanned_up_2025_04_19_16_42_08.json`



### Step 7️⃣ Purge Your Old Vault (Recommended)

To avoid duplication or leftover clutter, purge your existing vault before importing the cleaned one.

Visit: https://vault.bitwarden.com/#/settings/account

Scroll to “Purge Vault”, indtroduce masterpassword and confirm

⚠️ This action is irreversible — only do this if you're happy with the cleaned export or you still have access to the file you exported at step 1️⃣ Export Your Vaults




### Step 8️⃣ Import the Cleaned Vault

Visit: https://vault.bitwarden.com/#/tools/import

Choose Format: “JSON”

Upload the cleaned file you just generated

📌 Make sure you upload the one with the latest timestamp.




### Step 9️⃣ Not Happy with the Results?

No problem. You can always:

- Restart from Step 7️⃣ Purge Your New Vaul
- This time, at step 8️⃣ import the original vault_export.json file you exported at step 1️⃣ Export Your Vaults

You're fully in control of what gets imported.

---
## 📋 License

This project is licensed under the [MIT License](LICENSE).

You are free to:
- Use this script in personal or commercial projects
- Modify and redistribute it
- Adapt it to your needs

The license also includes a liability disclaimer:  
**You use this script at your own risk.**

---

## 🙋‍♂️ Disclaimer

This script was a one-off approach to solve a personal problem. If it works for you great... I'm happy for you. It's highly unlikely that I will maintain this script therefore this tool is provided **AS IS**, with **no support**, **no guarantees**, and **no warranty**.

You are responsible for:
- Backing up your original Bitwarden export files
- Inspecting the cleaned output before importing it
- Verifying that your vault behaves as expected after re-import

Always test with non-critical data if you're unsure.  
When in doubt, revert using your original export.
