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
