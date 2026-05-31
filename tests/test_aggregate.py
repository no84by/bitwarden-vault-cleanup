import bitwarden_vault_cleanup as bvc


def test_module_imports_without_running_main():
    assert hasattr(bvc, "deduplicate")
