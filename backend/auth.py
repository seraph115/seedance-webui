"""管理员凭据与会话鉴权。

首次启动自动生成强随机 admin 密码并打印到控制台；磁盘只存 PBKDF2 哈希。
会话签名密钥同样持久化到 data/admin.json，缺失时生成一次。
"""
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ADMIN_FILE = DATA_DIR / "admin.json"

PBKDF2_ITERATIONS = 240_000

# 登录限流（进程内）：连续失败达到阈值后锁定一段时间
_MAX_FAILS = 5
_LOCKOUT_SECONDS = 60
_fail_count = 0
_locked_until = 0.0


def _hash_password(password: str, salt: bytes, iterations: int) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex()


def _load() -> dict | None:
    if ADMIN_FILE.is_file():
        return json.loads(ADMIN_FILE.read_text(encoding="utf-8"))
    return None


def _save(record: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")


def ensure_admin() -> str | None:
    """确保 admin 凭据存在。首次生成时返回明文密码（供打印），否则返回 None。"""
    record = _load()
    if record and record.get("hash"):
        if not record.get("secret_key"):          # 兼容缺 secret_key 的旧文件
            record["secret_key"] = secrets.token_hex(32)
            _save(record)
        return None
    password = secrets.token_urlsafe(15)
    salt = secrets.token_bytes(16)
    _save({
        "salt": salt.hex(),
        "hash": _hash_password(password, salt, PBKDF2_ITERATIONS),
        "iterations": PBKDF2_ITERATIONS,
        "secret_key": secrets.token_hex(32),
    })
    return password


def get_secret_key() -> str:
    """返回持久化的会话签名密钥。

    约定：调用方应先调用 ensure_admin()。若此处发现凭据缺失而不得不生成，
    会同样打印一次性明文密码，避免密码被静默丢弃。
    """
    record = _load()
    if not record or not record.get("secret_key"):
        password = ensure_admin()
        if password:
            announce_password(password)
        record = _load()
    return record["secret_key"]


def announce_password(password: str) -> None:
    """把一次性明文密码醒目地打印到控制台。"""
    print("=" * 60)
    print(f"  ADMIN PASSWORD (save this): {password}")
    print("=" * 60)


def verify_password(password: str) -> bool:
    record = _load()
    if not record:
        return False
    salt = bytes.fromhex(record["salt"])
    actual = _hash_password(password, salt, int(record["iterations"]))
    return hmac.compare_digest(actual, record["hash"])


def check_not_locked() -> None:
    if _locked_until and time.monotonic() < _locked_until:
        raise HTTPException(status_code=429, detail="尝试过于频繁，请稍后再试")


def register_fail() -> None:
    global _fail_count, _locked_until
    _fail_count += 1
    if _fail_count >= _MAX_FAILS:
        _locked_until = time.monotonic() + _LOCKOUT_SECONDS
        _fail_count = 0


def register_success() -> None:
    global _fail_count, _locked_until
    _fail_count = 0
    _locked_until = 0.0


def require_auth(request: Request) -> None:
    if not request.session.get("authed"):
        raise HTTPException(status_code=401, detail="未登录")
