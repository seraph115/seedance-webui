import sys
from pathlib import Path

import pytest

# 让测试能 import backend/ 下的顶层模块（auth, config, settings_store, app...）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """把 auth / settings_store 的持久化目录指向临时目录，并复位登录限流。"""
    import auth
    d = tmp_path / "data"
    monkeypatch.setattr(auth, "DATA_DIR", d)
    monkeypatch.setattr(auth, "ADMIN_FILE", d / "admin.json")
    monkeypatch.setattr(auth, "_fail_count", 0, raising=False)
    monkeypatch.setattr(auth, "_locked_until", 0.0, raising=False)

    import settings_store
    monkeypatch.setattr(settings_store, "DATA_DIR", d)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", d / "settings.json")
    return d
