import bitwarden_vault_cleanup as bvc


def _login(id, uri="https://x.com", user="u", pw="p"):
    return {"id": id, "type": 1, "name": uri,
            "login": {"uris": [{"uri": uri, "match": None}], "username": user, "password": pw}}


def test_exclude_org_dupes_matches_by_content_not_id():
    personal = [_login("p-aaa", user="u", pw="p"),
                _login("p-bbb", uri="https://keep.com", user="v", pw="q")]
    org = [_login("o-zzz", user="u", pw="p")]
    kept = bvc.exclude_org_dupes(personal, org)
    kept_ids = {e["id"] for e in kept}
    assert "p-aaa" not in kept_ids
    assert "p-bbb" in kept_ids
