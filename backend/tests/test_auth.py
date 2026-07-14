import auth


def test_hash_verify_roundtrip(data_dir):
    pw = auth.ensure_admin()
    assert pw and isinstance(pw, str)
    assert auth.verify_password(pw) is True
    assert auth.verify_password("wrong-password") is False


def test_ensure_admin_is_idempotent(data_dir):
    pw1 = auth.ensure_admin()
    pw2 = auth.ensure_admin()
    assert pw1                      # 首次返回明文
    assert pw2 is None              # 再次调用不重新生成
    assert auth.verify_password(pw1) is True


def test_secret_key_is_stable(data_dir):
    auth.ensure_admin()
    assert auth.get_secret_key() == auth.get_secret_key()


def test_plaintext_never_persisted(data_dir):
    pw = auth.ensure_admin()
    raw = (data_dir / "admin.json").read_text(encoding="utf-8")
    assert pw not in raw


def test_login_throttle_locks_after_max_fails(data_dir):
    auth.ensure_admin()
    for _ in range(auth._MAX_FAILS):
        auth.register_fail()
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        auth.check_not_locked()
    assert exc.value.status_code == 429


def test_get_secret_key_announces_when_it_must_generate(data_dir, capsys):
    # 未先调用 ensure_admin() 时，get_secret_key 生成凭据并打印一次性账号密码
    key = auth.get_secret_key()
    assert key
    out = capsys.readouterr().out
    assert "ADMIN USERNAME:" in out
    assert "ADMIN PASSWORD (save this):" in out


def test_default_username_is_admin(data_dir):
    pw = auth.ensure_admin()
    assert auth.get_username() == "admin"
    assert auth.verify_credentials("admin", pw) is True
    assert auth.verify_credentials("wrong", pw) is False        # 用户名不对
    assert auth.verify_credentials("admin", "bad") is False     # 密码不对


def test_username_overridable_by_env(data_dir, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "seraph")
    pw = auth.ensure_admin()
    assert auth.get_username() == "seraph"
    assert auth.verify_credentials("seraph", pw) is True
    assert auth.verify_credentials("admin", pw) is False
