import bitwarden_vault_cleanup as bvc
import os

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_module_imports_without_running_main():
    assert hasattr(bvc, "deduplicate")


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


def test_scan_for_exports_finds_and_classifies(tmp_path):
    import shutil
    for fn in ("chromium.csv", "bitwarden.json", "random.csv"):
        shutil.copy(os.path.join(FX, fn), tmp_path / fn)
    found = bvc.scan_for_exports([str(tmp_path)])
    kinds = sorted(k for _, k in found)
    assert kinds == ["bitwarden_json", "chromium_csv"]   # random.csv (None) excluded


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
    assert ff["name"] == "site.org"
    sf = bvc.csv_to_items(os.path.join(FX, "safari.csv"), "safari_csv")[0]
    assert sf["login"]["username"] == "dave" and sf["name"] == "MyBank"


def test_detect_browsers_presence_only(tmp_path, monkeypatch):
    # create a fake firefox profile dir under a fake linux home
    (tmp_path / ".mozilla" / "firefox").mkdir(parents=True)
    monkeypatch.setattr(bvc.platform, "system", lambda: "Linux")
    found = bvc.detect_browsers(home=str(tmp_path))
    assert "firefox" in found
    assert "chrome" not in found          # its dir does not exist


def test_downloads_dir_prefers_existing(tmp_path, monkeypatch):
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(bvc.os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    assert bvc.downloads_dir().endswith("Downloads")


def test_export_instructions_known_browser_mentions_export():
    text = bvc.export_instructions("chrome")
    assert "export" in text.lower()


def test_collect_source_returns_watched_file():
    def fake_watch(kinds, since):
        return os.path.join(FX, "chromium.csv")     # appears immediately
    path = bvc.collect_source("chrome", expected_kinds={"chromium_csv"},
                              watch=fake_watch, ask=lambda prompt: "", now=lambda: 0.0,
                              info=lambda *_: None)
    assert path.endswith("chromium.csv")


def test_collect_source_timeout_then_skip_returns_none():
    def fake_watch(kinds, since):
        return None                                  # never appears
    path = bvc.collect_source("chrome", expected_kinds={"chromium_csv"},
                              watch=fake_watch, ask=lambda prompt: "", now=lambda: 999.0,
                              timeout=0.0, info=lambda *_: None)
    assert path is None


def test_collect_source_accepts_pasted_path():
    def fake_watch(kinds, since):
        return None
    pasted = os.path.join(FX, "firefox.csv")
    path = bvc.collect_source("firefox", expected_kinds={"firefox_csv"},
                              watch=fake_watch, ask=lambda prompt: pasted, now=lambda: 999.0,
                              timeout=0.0, info=lambda *_: None)
    assert path == pasted


def test_aggregate_sources_merges_found_files():
    found = [
        (os.path.join(FX, "bitwarden.json"), "bitwarden_json"),
        (os.path.join(FX, "chromium.csv"), "chromium_csv"),
    ]
    items, sources = bvc.aggregate_sources(found=found, installed=set(),
                                           confirm=lambda *_: True,
                                           collect=lambda *a, **k: None)
    assert len(items) == 2                     # chromium only; bitwarden loaded by main()
    assert sources["bitwarden_json"] == 1 and sources["chromium_csv"] == 2
    assert all(it.get("id") for it in items)


def test_aggregate_sources_declined_returns_empty():
    items, sources = bvc.aggregate_sources(found=[], installed=set(),
                                           confirm=lambda *_: False, collect=lambda *a, **k: None)
    assert items == [] and sources == {}


def test_end_to_end_aggregate_then_dedup_collapses_overlap():
    # bitwarden.json has example.com/alice/pw1; chromium.csv ALSO has example.com/alice/pw1
    # (exact dup -> collapses) plus NoUrlRow/bob (browser-only -> preserved via passthrough)
    bw_items = bvc.load_vault(os.path.join(FX, "bitwarden.json"))["items"]
    browser_items, _ = bvc.aggregate_sources(
        found=[(os.path.join(FX, "chromium.csv"), "chromium_csv")],
        installed=set(), confirm=lambda *_: True, collect=lambda *a, **k: None)
    items = bw_items + browser_items
    non_login = [e for e in items if 'login' not in e]
    passkey = [e for e in items if 'login' in e and bvc.has_passkey(e)]
    dedup_in = [e for e in items if 'login' in e and not bvc.has_passkey(e)]
    no_url = [e for e in dedup_in if not e['login'].get('uris')]
    with_url = [e for e in dedup_in if e['login'].get('uris')]
    cleaned, _skipped = bvc.clean_entries(with_url, [])
    reused = bvc.index_passwords(cleaned)
    deduped, merged, removed = bvc.deduplicate(cleaned, reused)
    names = sorted(e['name'] for e in deduped)
    assert "example.com" in names
    assert removed == 1                       # the exact duplicate was removed
    assert any(e['login'].get('username') == 'bob' for e in no_url)   # browser-only preserved
