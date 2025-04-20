# bitwarden-vault-cleanup
Python script to clean, normalize, and deduplicate Bitwarden vault exports.  Merges related entries, removes identical duplicates, excludes organization vault items, and outputs an import-ready JSON file —  all while running locally, without storing, transmitting, or collecting any sensitive data. An one commmand-line, low-tech skill, and fully under user control solution — no cloud magic, ai or some else's webpage.

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
   - If one password is reused across other entries (will be considered potentially compromised), a unique passwords will be preferred.
   - Reused passwords are still retained if they have the newer revision date.

4. **creationDate**  
   If all other fields are equal, the newest entry by creation timestamp is kept.

5. **Fallback: first entry**  
   If all entries are identical in all relevant fields, the first one (sorted by ID) is kept and the rest are deleted.

<details>
<summary>🧠 Additional algorithm details here</summary>

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

All decision-making is logged visibly in the terminal, and a summary is printed at the end for user's review.
</details>

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

### Step 0️⃣ Prepare Your Environment
- Create a working folder
- Download the script https://github.com/no84by/bitwarden-vault-cleanup/blob/main/bitwarden_vault_cleanup.py
- Install Python (if needed)

<details>
<summary>💡 (Optional but recommended) Import all saved passwords from your browsers into Bitwarden</summary>

This step ensures that all credentials — even from browsers you may have forgotten about — are included in the cleanup process.

#### Export login data from your browsers:

- **Google Chrome / Microsoft Edge / Brave**:  
  `Settings → Autofill → Password Manager → ⋮ (3-dot menu) → Export passwords`  
  → Save as a `.csv` file

- **Mozilla Firefox**:  
  `Logins and Passwords → ⋯ (top-right menu) → Export Logins`  
  → Save as a `.csv` file

- **Apple Safari (macOS)**:  
  `Safari → Preferences → Passwords → ... → Export Passwords`  
  → Save as a `.csv` file (you may need to enter your macOS password)

#### Import into Bitwarden:

- Go to the [Bitwarden Web Vault](https://vault.bitwarden.com/)
- Navigate to `Tools → Import Data`
- Choose the appropriate browser or format from the dropdown
- Upload your `.csv` file and complete the import

> 🛑 Don’t worry about duplicates or messy entries — the cleanup script will take care of that.
</details>

### Step 1️⃣ Export Your Vaults
Export your vault(s) using the official Bitwarden web vault:

- Personal Vault:  
  `https://vault.bitwarden.com/#/tools/export`

- Organization Vault (if applicable, and only with vault admin rights):  
  `https://vault.bitwarden.com/#/organizations/<ORG-ID>/settings/tools/export`

> ⚠️ Choose the **“JSON”** format — **NOT** “JSON (Encrypted)”



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

Output to file instead of on the terminal screen:
```powershell
python bitwarden_vault_cleanup.py vault_export.json vault_org_export.json  > output.log
```


### Step 6️⃣ Review the Output
Console output will display the progress
- Initial personal entries
- Organizational entries provided
- Total processed entries
- Entires with potentially compromised passwords
- Duplicate entries merged
- Duplicate entries removed
- Ambiguous entries retained           
- Ommited login entries that slipped cleanup
- Final kept entries (for import)
- Final vault item type breakdown:
     • Logins
     • Secure Notes
     • Cards
     • Identities
- Folder breakdown (logins only):
     • [no folder]
     • firstname.lastname
     • nickname
     • random.alias

<details>
<summary>Here’s a sanitized example of an actual terminal output</summary>

```plaintext
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.joinhoney.com (e20428c6-a8f0-471d-96e6-c9d567874778)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.joinhoney.com (4faf4187-f47f-4cae-b5fa-c9d567879a53)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.laudamotion.com (2ac5feb0-473f-4581-80de-ae3600a40a58)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.laudamotion.com (8957a074-d6e7-447b-9583-c9d567874778)
Assigned folder random.alias (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.mediafire.com (4123764c-48f1-4a3e-a769-c9d567874778)
Assigned folder random.alias (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.mediafire.com (45e0a887-a9ee-4c02-88f5-c9d567879a53)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.messenger.com (620cbefb-7bbd-4b58-b5da-ae3600a40a58)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.messenger.com (c82abbbb-0373-4c72-a201-c9d567874778)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.messenger.com (c1089bfb-bbc8-4695-8fc4-c9d567879a53)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.michaelpage.com (d307e0a8-e6c5-4d1e-889f-ae3600a40a58)
Assigned folder random.alias (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.mindmeister.com (a318c0f1-b799-4b61-ac57-c9d567874778)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.mindmeister.com (4447abcf-7a3f-4865-b376-c9d567879a53)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.netflix.com (0e2d8f41-04b3-458c-802a-ae3600a40a58)
Assigned folder nickname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.netflix.com (b701e4db-ec96-444a-8338-c9d567874778)
Assigned folder nickname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.netflix.com (45606a49-e28b-4a82-bb09-c9d567879a53)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.numan.com (60ee9039-1afd-4ba1-9560-c9d567874778)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.openstreetmap.org (4c572d88-9040-4e02-be79-ae3600a40a58)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.openstreetmap.org (0f886f06-f3cf-495f-ba25-c9d567874778)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.openstreetmap.org (38476a60-adee-401e-801c-c9d567879a53)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.partneragencies.org (cf6ef168-1dee-4dc5-9463-ae3600a40a58)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to www.partneragencies.org (3cb96b94-fe0b-42f4-8a60-c9d567874778)

[truncated]

Assigned folder nickname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to zapier.com (5f490c0d-7c2a-470b-9fdd-ae3600a40a59)
Assigned folder random.alias (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to zapier.com (7dcfd77a-f29d-4552-886c-ae3600a453f1)
Assigned folder random.alias (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to zapier.com (c56fc854-89b7-482b-a95c-c9d567874778)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to zapier.com (9a49fbeb-42f2-45fc-92f3-c9d56787682c)
Assigned folder firstname.lastname (91cbbeb9-45ee-4299-b8ab-ab1234cd4ae3) to zapier.com (24ab6c50-59e0-45e3-a206-c9d567879a53)

[INFO] Starting vault clean-up...

--------------------------------------------

Evaluating group:
 com.sample.bundle
  Username: 8374938273
  Entries: 3
→ Merged 3 entries into: samplebundle.com (45a6d77f-da5e-4184-8abf-fedcba098765)
   └─ Total merged URIs: 1

--------------------------------------------

Evaluating group:
 org.random.app
  Username: firstname.lastname
  Entries: 3
→ Merged 3 entries into: randomapp.org (ae9bbbe8-0e3c-413a-bd6a-abcdef123456)
   └─ Total merged URIs: 1

--------------------------------------------

Evaluating group:
 net.fake.bundle
  Username: random.alias
  Entries: 3
→ Merged 3 entries into: fakebundle.net (05f5ec20-de75-4dab-b15e-fedcba654321)
   └─ Total merged URIs: 1

--------------------------------------------

Evaluating group:
 www.obfuscated.com
  Username: firstname.lastname@email.com
  Entries: 2
→ Merged 2 entries into: obfuscated.com (38e5b98d-4959-4488-9855-a1b2c3d4e5f6)
   └─ Total merged URIs: 3
   └─ Notes retained (10 lines)

--------------------------------------------

Evaluating group:
 www.example5.com
  Username: user123@provider.com
  Entries: 5
→ Merged 5 entries into: www.example5.com (87249f4d-a5b4-45e0-9031-abc123def456)
   └─ Total merged URIs: 2

--------------------------------------------

[truncated]

--------------------------------------------

Evaluating group:
 www.example5.com
  Username: random.alias@provider.com
  Entries: 5
→ Merged 5 entries into: www.example5.com (87249f4d-a5b4-45e0-9031-abc123def456)
   └─ Total merged URIs: 2

--------------------------------------------

Evaluating group:
 feedback.something.net
  Username: admin
  Entries: 5
→ Merged 5 entries into: http://feedback.something.net (6467348a-a10c-4788-9798-a1b2c3d4e5f6)
   └─ Total merged URIs: 2

--------------------------------------------

Evaluating group:
 zoom.example
  Username: random.alias
  Entries: 5
→ Merged 5 entries into: zoom.example (ad61512c-b5d6-40ef-9081-b1c2d3e4f5g6)
   └─ Total merged URIs: 2

--------------------------------------------

Evaluating group:
 www.scholarhub.org
  Username: knowledge
  Entries: 2
→ Merged 2 entries into: scholarhub.org (cff178c9-26ad-4c88-a18d-abcdef654321)
   └─ Total merged URIs: 1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CLEAN-UP SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Initial personal entries:                            3931
Organizational entries provided:                     26
Total processed entries:                             1267
Entires with potentially compromised passwords:      163
Duplicate entries merged:                            2634
Duplicate entries removed:                           5
Ambiguous entries retained:                          0
Ommited login entries that slipped cleanup:          25
Final kept entries (for import):                     1277


  >> Final vault item type breakdown:
     • Logins: 1267 entries
     • Secure Notes: 7 entries
     • Cards: 2 entries
     • Identities: 1 entries


  >> Folder breakdown (logins only):
     • [no folder]: 579 entries
     • firstname.lastname: 483 entries
     • nickname: 191 entries
     • random.alias: 14 entries

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[DEBUG] Reused passwords: 163. Top reused passwords:
               • abcdefghjk(1518)
               • lmnopqrs(185)
               • tuzxwyq(39)
               • password(29)
               • h)s5TrCkRM%ng2nFS/A(25)
               • %=32Xr#avtawe8z(24)
               • billyjoel(24)
               • tembelionj(23)
               • partenvarson(22)
               • nF@TUruv36rE6j@(21)
               • 6mZpZwQbW6vkZl3T(20)
               • V0PpCsNts1mSystem32(20)
               • xp5nP6Bv(18)
               • admin(17)
               • cka12V31B(16)

[INFO] Cleaned vault written to: vault_export_cleanned_up_YYYY_MM_DD_HH_MM_SS.json

PS C:\Users\username\Downloads\Bitwarden>
```
</details>

The script creates in the same folder a new JSON file named like: `vault_export_cleanned_up_YYYY_MM_DD_HH_MM_SS.json`



### Step 7️⃣ Purge Your Old Vault (Recommended)

To avoid duplication or leftover clutter, purge your existing vault before importing the cleaned one.

Visit: https://vault.bitwarden.com/#/settings/account

Scroll to “Purge Vault”, indtroduce masterpassword and confirm

> ⚠️ This action is irreversible — only do this if you're happy with the cleaned export or you still have access to the file you exported at step 1️⃣ Export Your Vaults




### Step 8️⃣ Import the Cleaned Vault

Visit: https://vault.bitwarden.com/#/tools/import

Choose Format: “JSON”

Upload the cleaned file you just generated

> 📌 Make sure you upload the one with the latest timestamp.




### Step 9️⃣ Not Happy with the Results?

No problem. You can always:

- Restart from Step 7️⃣ Purge Your New Vaul
- This time, at step 8️⃣ import the original vault_export.json file you exported at step 1️⃣ Export Your Vaults

You're fully in control of what gets imported.


### 🔟 Clean Up Your Files (Highly Recommended)

Once you're happy with your cleaned vault and have successfully imported it into Bitwarden:

> 🧽 **Delete all exported `.json` files** from your computer — both the original and the cleaned version.

These files contain all your credentials in plain text and can be dangerous if left behind.

## 📌 Passwords stored in plaintext are a major security risk.  
Always remove export files when you're done.


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
When in doubt, revert using your original export json.
