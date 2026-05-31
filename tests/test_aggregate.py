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
