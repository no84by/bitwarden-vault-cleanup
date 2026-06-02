import bitwarden_vault_cleanup as bvc


def _login(id, uri="https://x.com", user="u", pw="p", totp=None, notes=None, fields=None,
           rev="2026-01-01T00:00:00.000Z"):
    e = {"id": id, "type": 1, "name": "x", "notes": notes,
         "revisionDate": rev, "creationDate": rev,
         "login": {"uris": [{"uri": uri, "match": None}], "username": user, "password": pw,
                   "totp": totp, "fido2Credentials": []}}
    if fields is not None:
        e["fields"] = fields
    return e


def test_merge_unions_fields_and_preserves_both_totps():
    a = _login("1", totp="SEED-A", fields=[{"name": "recovery", "value": "AAA", "type": 1}])
    b = _login("2", totp="SEED-B", fields=[{"name": "pin", "value": "BBB", "type": 0}])
    final, merged, removed = bvc.deduplicate([a, b], compromised_passwords=set())
    assert merged == 1 and len(final) == 1
    m = final[0]
    assert {"recovery", "pin"} <= {f["name"] for f in m["fields"]}
    seeds = {m["login"]["totp"]} | {f["value"] for f in m["fields"] if "totp" in f["name"]}
    assert {"SEED-A", "SEED-B"} <= seeds


def test_same_timestamps_differing_fields_still_merge_not_dropped():
    # identical dates but different custom fields -> must MERGE (union), not keep-first-and-drop.
    a = _login("1", fields=[{"name": "k1", "value": "v1", "type": 1}])
    b = _login("2", fields=[{"name": "k2", "value": "v2", "type": 1}])
    final, merged, removed = bvc.deduplicate([a, b], compromised_passwords=set())
    assert merged == 1 and removed == 0
    assert {"k1", "k2"} <= {f["name"] for f in final[0]["fields"]}


def test_truly_identical_entries_are_kept_first_not_merged():
    a = _login("1", fields=[{"name": "k", "value": "v", "type": 1}])
    b = _login("2", fields=[{"name": "k", "value": "v", "type": 1}])
    final, merged, removed = bvc.deduplicate([a, b], compromised_passwords=set())
    assert removed == 1 and merged == 0 and len(final) == 1
