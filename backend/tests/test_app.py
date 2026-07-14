import importlib
import sys

import pytest


@pytest.fixture
def client(data_dir, monkeypatch):
    """在临时 data 目录下创建 admin，再全新加载 app，返回 (TestClient, 用户名, 明文密码)。"""
    import auth
    password = auth.ensure_admin()          # 先建凭据，拿到明文
    username = auth.get_username()           # 默认 admin
    if "app" in sys.modules:
        app_module = importlib.reload(sys.modules["app"])
    else:
        import app as app_module
    from starlette.testclient import TestClient
    return TestClient(app_module.app), username, password


def test_protected_requires_login(client):
    c, _, _ = client
    assert c.get("/api/models").status_code == 401


def test_login_flow(client):
    c, username, password = client
    # 错误密码 → 401
    assert c.post("/api/login", json={"username": username, "password": "nope"}).status_code == 401
    # 错误用户名 → 401
    assert c.post("/api/login", json={"username": "wrong", "password": password}).status_code == 401
    # 正确账号密码 → 200
    assert c.post("/api/login", json={"username": username, "password": password}).status_code == 200
    assert c.get("/api/models").status_code == 200        # cookie 持久化后放行
    c.post("/api/logout")
    assert c.get("/api/models").status_code == 401


def test_settings_roundtrip(client):
    c, username, password = client
    c.post("/api/login", json={"username": username, "password": password})
    r = c.put("/api/settings", json={"api_key": "sk-abcdef2345"})
    assert r.status_code == 200
    body = c.get("/api/settings").json()
    assert body["api_key_source"] == "file"
    assert body["api_key_masked"] == "sk-…2345"
    assert "sk-abcdef2345" not in str(body)


def test_generate_requires_configured_key(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "API_KEY", "")               # 无 env、无文件
    c, username, password = client
    c.post("/api/login", json={"username": username, "password": password})
    r = c.post("/api/generate", json={"mode": "text", "prompt": "hi"})
    assert r.status_code == 400
    assert "API_KEY" in r.json()["detail"]
