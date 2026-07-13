import config
import settings_store


def test_file_value_overrides_env(data_dir, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "env-key")
    assert settings_store.get_api_key() == "env-key"          # 无文件 → 回退 env
    settings_store.set_settings(api_key="file-key")
    assert settings_store.get_api_key() == "file-key"         # 文件优先


def test_api_base_fallback_and_override(data_dir, monkeypatch):
    monkeypatch.setattr(config, "API_BASE", "https://env.example")
    assert settings_store.get_api_base() == "https://env.example"
    settings_store.set_settings(api_base="https://file.example")
    assert settings_store.get_api_base() == "https://file.example"


def test_describe_masks_key_and_reports_source(data_dir, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    assert settings_store.describe()["api_key_source"] == "unset"

    monkeypatch.setattr(config, "API_KEY", "sk-envenvenvenv")
    assert settings_store.describe()["api_key_source"] == "env"

    settings_store.set_settings(api_key="sk-abcdef2345")
    d = settings_store.describe()
    assert d["api_key_source"] == "file"
    assert d["api_key_masked"] == "sk-…2345"                  # 全 key 不出现
    assert "sk-abcdef2345" != d["api_key_masked"]


def test_set_settings_merges_fields(data_dir):
    settings_store.set_settings(api_key="k1")
    settings_store.set_settings(api_base="https://b")
    assert settings_store.get_api_key() == "k1"               # 只改 base 不清空 key
    assert settings_store.get_api_base() == "https://b"
