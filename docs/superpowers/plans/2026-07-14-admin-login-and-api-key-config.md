# Admin Login + Page-Configured API_KEY Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the SeeDance WebUI behind a single-admin login and let the admin configure the upstream API_KEY (and API_BASE) from a Settings panel, persisted to a local file.

**Architecture:** FastAPI gains a small credentials module (PBKDF2 hashing, auto-generated password printed on first boot) and a settings store (file-over-env). Session auth uses Starlette `SessionMiddleware` (HttpOnly signed cookie). The Vue SPA gains a `useAuth` composable that gates the app behind a `LoginView`, plus a `SettingsDialog` for the API key. No router and no database are introduced.

**Tech Stack:** Python 3.11 / FastAPI / Starlette `SessionMiddleware` / stdlib `hashlib` PBKDF2 / pytest + httpx (TestClient); Vue 3 + Element Plus + axios.

## Global Constraints

- Backend runtime dir layout: modules live in `backend/`, persisted state in `<repo>/data/` (i.e. `Path(__file__).resolve().parent.parent / "data"` from a `backend/` module). In Docker this is `/app/data`.
- Password plaintext is NEVER written to disk — only a PBKDF2-HMAC-SHA256 salted hash.
- API key is NEVER returned in full by any endpoint — only masked (`sk-…QlT`).
- File-configured value ALWAYS takes precedence over the env var; env is the fallback/default.
- Single admin account only. No password-change-from-UI, no multi-user (v1 non-goals).
- Session cookie: HttpOnly (default), `same_site="lax"`, signed with a persisted secret key.
- Dev backend runs on port **8008** (the Vite proxy in `frontend/vite.config.js` targets `http://127.0.0.1:8008`). Production/Docker runs uvicorn on 8000.
- Follow existing file style: module docstrings in Chinese, keyword-only helpers, small focused files.

---

### Task 1: Admin credential store + backend test tooling

**Files:**
- Create: `backend/auth.py`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`

**Interfaces:**
- Produces:
  - `auth.DATA_DIR: Path`, `auth.ADMIN_FILE: Path`
  - `auth.ensure_admin() -> str | None` (returns plaintext password on first creation, else `None`)
  - `auth.verify_password(password: str) -> bool`
  - `auth.get_secret_key() -> str`
  - `auth.require_auth(request: Request) -> None` (FastAPI dependency; raises 401)
  - `auth.check_not_locked() -> None`, `auth.register_fail() -> None`, `auth.register_success() -> None`

- [ ] **Step 1: Add dependencies**

Append to `backend/requirements.txt` (keep existing lines):

```
itsdangerous>=2.1
```

Create `backend/requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 2: Install dev deps**

Run: `cd backend && pip install -r requirements-dev.txt`
Expected: installs pytest, httpx, itsdangerous without error.

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/conftest.py`:

```python
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
    return d
```

Create `backend/tests/test_auth.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'auth'` (module not created yet).

- [ ] **Step 5: Implement `backend/auth.py`**

```python
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
    record = _load()
    if not record or not record.get("secret_key"):
        ensure_admin()
        record = _load()
    return record["secret_key"]


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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/auth.py backend/tests/__init__.py backend/tests/conftest.py backend/tests/test_auth.py backend/requirements.txt backend/requirements-dev.txt
git commit -m "feat(backend): admin credential store with PBKDF2 + login throttle"
```

---

### Task 2: Settings store (API_KEY / API_BASE persistence)

**Files:**
- Create: `backend/settings_store.py`
- Create: `backend/tests/test_settings_store.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `config.API_KEY`, `config.API_BASE` (from `backend/config.py`)
- Produces:
  - `settings_store.DATA_DIR: Path`, `settings_store.SETTINGS_FILE: Path`
  - `settings_store.get_api_key() -> str`
  - `settings_store.get_api_base() -> str`
  - `settings_store.set_settings(api_key: str | None = None, api_base: str | None = None) -> None`
  - `settings_store.describe() -> dict` → `{"api_key_masked": str, "api_key_source": "file"|"env"|"unset", "api_base": str}`

- [ ] **Step 1: Extend the `data_dir` fixture to also patch settings_store**

In `backend/tests/conftest.py`, inside the `data_dir` fixture, add these lines before `return d`:

```python
    import settings_store
    monkeypatch.setattr(settings_store, "DATA_DIR", d)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", d / "settings.json")
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_settings_store.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_settings_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'settings_store'`.

- [ ] **Step 4: Implement `backend/settings_store.py`**

```python
"""运行期可配置项（API_KEY / API_BASE）的读写与持久化。

优先级：data/settings.json 中的值 > 环境变量（经 config 读取的默认值）。
"""
import json
from pathlib import Path

import config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


def _load() -> dict:
    if SETTINGS_FILE.is_file():
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_api_key() -> str:
    return (_load().get("api_key") or "").strip() or config.API_KEY


def get_api_base() -> str:
    return (_load().get("api_base") or "").strip() or config.API_BASE


def set_settings(api_key: str | None = None, api_base: str | None = None) -> None:
    data = _load()
    if api_key is not None:
        data["api_key"] = api_key.strip()
    if api_base is not None:
        data["api_base"] = api_base.strip()
    _save(data)


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 7:
        return "…" + key[-2:]
    return key[:3] + "…" + key[-4:]


def describe() -> dict:
    file_key = (_load().get("api_key") or "").strip()
    if file_key:
        source = "file"
    elif config.API_KEY:
        source = "env"
    else:
        source = "unset"
    return {
        "api_key_masked": _mask(get_api_key()),
        "api_key_source": source,
        "api_base": get_api_base(),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_settings_store.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/settings_store.py backend/tests/test_settings_store.py backend/tests/conftest.py
git commit -m "feat(backend): settings store with file-over-env API key/base"
```

---

### Task 3: Route upstream calls through the settings store

**Files:**
- Modify: `backend/seedance.py` (imports; `_headers()`; `submit()` URL; `query()` URL)
- Create: `backend/tests/test_seedance_headers.py`

**Interfaces:**
- Consumes: `settings_store.get_api_key()`, `settings_store.get_api_base()`
- Produces: `seedance._headers()` reads the live key; `submit`/`query` use the live base URL.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_seedance_headers.py`:

```python
import seedance
import settings_store


def test_headers_read_live_key(monkeypatch):
    monkeypatch.setattr(settings_store, "get_api_key", lambda: "live-key-123")
    assert seedance._headers()["Authorization"] == "Bearer live-key-123"
    assert seedance._headers()["Content-Type"] == "application/json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_seedance_headers.py -v`
Expected: FAIL — current `_headers()` returns `Bearer ` (empty, from `config.API_KEY`) so the assertion mismatches.

- [ ] **Step 3: Edit `backend/seedance.py`**

Add the import next to the existing `import config` (line 12):

```python
import config
import settings_store
```

Replace `_headers()` (currently lines 119-123):

```python
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings_store.get_api_key()}",
        "Content-Type": "application/json",
    }
```

In `submit()` replace the URL line (currently line 54):

```python
    url = f"{settings_store.get_api_base()}/v1/video/generations"
```

In `query()` replace the URL line (currently line 86):

```python
    url = f"{settings_store.get_api_base()}/v1/video/generations/{task_id}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_seedance_headers.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/seedance.py backend/tests/test_seedance_headers.py
git commit -m "refactor(backend): read API key/base from settings store at call time"
```

---

### Task 4: Auth + settings endpoints and route protection

**Files:**
- Modify: `backend/app.py`
- Create: `backend/tests/test_app.py`

**Interfaces:**
- Consumes: `auth.*` (Task 1), `settings_store.*` (Task 2)
- Produces (HTTP):
  - `POST /api/login {password}` → `{ok:true}` / 401 / 429
  - `POST /api/logout` → `{ok:true}`
  - `GET /api/session` → `{authed:bool}` (open)
  - `GET /api/settings` → `describe()` (auth)
  - `PUT /api/settings {api_key?, api_base?}` → `describe()` (auth)
  - `GET /api/models`, `POST /api/generate`, `GET /api/status/{id}` now require auth; `generate` 400s if no key configured.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_app.py`:

```python
import importlib
import sys

import pytest


@pytest.fixture
def client(data_dir, monkeypatch):
    """在临时 data 目录下创建 admin，再全新加载 app，返回 (TestClient, 明文密码)。"""
    import auth
    password = auth.ensure_admin()          # 先建凭据，拿到明文
    if "app" in sys.modules:
        app_module = importlib.reload(sys.modules["app"])
    else:
        import app as app_module
    from starlette.testclient import TestClient
    return TestClient(app_module.app), password


def test_protected_requires_login(client):
    c, _ = client
    assert c.get("/api/models").status_code == 401


def test_login_flow(client):
    c, password = client
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    assert c.post("/api/login", json={"password": password}).status_code == 200
    assert c.get("/api/models").status_code == 200        # cookie 持久化后放行
    c.post("/api/logout")
    assert c.get("/api/models").status_code == 401


def test_settings_roundtrip(client):
    c, password = client
    c.post("/api/login", json={"password": password})
    r = c.put("/api/settings", json={"api_key": "sk-abcdef2345"})
    assert r.status_code == 200
    body = c.get("/api/settings").json()
    assert body["api_key_source"] == "file"
    assert body["api_key_masked"] == "sk-…2345"
    assert "sk-abcdef2345" not in str(body)


def test_generate_requires_configured_key(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "API_KEY", "")               # 无 env、无文件
    c, password = client
    c.post("/api/login", json={"password": password})
    r = c.post("/api/generate", json={"mode": "text", "prompt": "hi"})
    assert r.status_code == 400
    assert "API_KEY" in r.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_app.py -v`
Expected: FAIL — endpoints/protection not present (e.g. `/api/login` 404, `/api/models` returns 200 without auth).

- [ ] **Step 3: Edit imports in `backend/app.py`**

Replace the FastAPI import line (currently line 13):

```python
from fastapi import FastAPI, HTTPException, Depends, Request
```

Add after the existing `import seedance` (line 19):

```python
from starlette.middleware.sessions import SessionMiddleware

import auth
import settings_store
```

- [ ] **Step 4: Add startup password print + SessionMiddleware in `backend/app.py`**

Immediately after `app = FastAPI(title="SeeDance 视频生成测试台")` (line 21), insert:

```python
# 首次启动生成并打印 admin 密码（仅一次），并装配签名 Cookie 会话
_first_run_pw = auth.ensure_admin()
if _first_run_pw:
    print("=" * 60)
    print(f"  ADMIN PASSWORD (save this): {_first_run_pw}")
    print("=" * 60)

app.add_middleware(
    SessionMiddleware,
    secret_key=auth.get_secret_key(),
    same_site="lax",
    https_only=False,
)
```

- [ ] **Step 5: Add auth + settings endpoints in `backend/app.py`**

Add these models after the existing `GenerateRequest` class (after line 40):

```python
class LoginRequest(BaseModel):
    password: str


class SettingsRequest(BaseModel):
    api_key: str | None = None
    api_base: str | None = None
```

Add these routes just before the static-mount block (before the `# ---- 托管前端构建产物` comment, ~line 84):

```python
@app.post("/api/login")
def login(req: LoginRequest, request: Request):
    """校验密码，成功则在会话里置 authed。"""
    auth.check_not_locked()
    if not auth.verify_password(req.password):
        auth.register_fail()
        raise HTTPException(status_code=401, detail="密码错误")
    auth.register_success()
    request.session["authed"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/session")
def session_state(request: Request):
    return {"authed": bool(request.session.get("authed"))}


@app.get("/api/settings", dependencies=[Depends(auth.require_auth)])
def read_settings():
    return settings_store.describe()


@app.put("/api/settings", dependencies=[Depends(auth.require_auth)])
def write_settings(req: SettingsRequest):
    settings_store.set_settings(api_key=req.api_key, api_base=req.api_base)
    return settings_store.describe()
```

- [ ] **Step 6: Protect the three existing endpoints in `backend/app.py`**

Change the decorators:

```python
@app.get("/api/models", dependencies=[Depends(auth.require_auth)])
```

```python
@app.post("/api/generate", dependencies=[Depends(auth.require_auth)])
```

```python
@app.get("/api/status/{task_id}", dependencies=[Depends(auth.require_auth)])
```

Inside `generate()`, after the empty-prompt check and before `payload = seedance.build_payload(`:

```python
    if not settings_store.get_api_key():
        raise HTTPException(status_code=400, detail="请先在设置中配置 API_KEY")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS (all backend tests across Tasks 1-4 green).

- [ ] **Step 8: Commit**

```bash
git add backend/app.py backend/tests/test_app.py
git commit -m "feat(backend): login/logout/session + settings endpoints, protect API"
```

---

### Task 5: Frontend API client — cookies, auth/settings calls, 401 handling

**Files:**
- Modify: `frontend/src/api.js`

**Interfaces:**
- Produces (named exports):
  - existing: `fetchOptions()`, `generate(payload)`, `fetchStatus(taskId)`
  - new: `login(password)`, `logout()`, `getSession()`, `getSettings()`, `saveSettings(payload)`
- Behavior: axios instance uses `withCredentials: true`; a response interceptor flips the shared `authed` ref to `false` on any HTTP 401 (via dynamic import to avoid a circular dependency with `useAuth`).

- [ ] **Step 1: Replace `frontend/src/api.js` with the full updated file**

```javascript
import axios from 'axios'

// 与后端同源；开发时由 Vite proxy 转发到 :8008。带上 Cookie 以携带会话。
const http = axios.create({ baseURL: '/api', timeout: 200000, withCredentials: true })

// 统一错误信息；遇到 401 把全局登录态切回未登录（动态 import 避免与 useAuth 循环依赖）
http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      import('./composables/useAuth').then((m) => {
        m.authed.value = false
      })
    }
    const detail = err?.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(detail))
  }
)

export function fetchOptions() {
  return http.get('/models').then((r) => r.data)
}

// payload: { mode, prompt, duration, resolution, model, first_frame?, last_frame?, images? }
export function generate(payload) {
  return http.post('/generate', payload).then((r) => r.data)
}

export function fetchStatus(taskId) {
  return http.get(`/status/${taskId}`).then((r) => r.data)
}

// ---- 鉴权 ----
export function login(password) {
  return http.post('/login', { password }).then((r) => r.data)
}

export function logout() {
  return http.post('/logout').then((r) => r.data)
}

export function getSession() {
  return http.get('/session').then((r) => r.data)
}

// ---- 设置 ----
export function getSettings() {
  return http.get('/settings').then((r) => r.data)
}

export function saveSettings(payload) {
  return http.put('/settings', payload).then((r) => r.data)
}
```

- [ ] **Step 2: Verify the frontend still builds**

Run: `cd frontend && npm run build`
Expected: build succeeds. The dynamic `import('./composables/useAuth')` is a lazy chunk resolved at runtime (created in Task 6); Vite builds it as a code-split chunk and does not fail if invoked only on a 401. (When executing strictly in order, Task 6 creates the composable next.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(frontend): send session cookie, add auth/settings API calls, 401 handling"
```

---

### Task 6: Auth composable, login view, and app gate

**Files:**
- Create: `frontend/src/composables/useAuth.js`
- Create: `frontend/src/components/LoginView.vue`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `login`, `logout`, `getSession` from `../api` (Task 5)
- Produces:
  - `useAuth.js` module exports the shared refs `authed` and `ready`, and `useAuth()` returning `{ authed, ready, checkSession, login, logout }`
  - `LoginView.vue` (self-contained; calls `useAuth().login`)
  - `App.vue` renders `LoginView` when unauthenticated, the existing grid when authenticated, and resumes history polling only after auth.

- [ ] **Step 1: Create `frontend/src/composables/useAuth.js`**

```javascript
import { ref } from 'vue'
import { login as apiLogin, logout as apiLogout, getSession } from '../api'

// 模块级单例：全应用共享同一份登录状态（api.js 的 401 拦截器也会改它）
export const authed = ref(false)
export const ready = ref(false) // 首次会话检查完成前为 false

export function useAuth() {
  async function checkSession() {
    try {
      const { authed: a } = await getSession()
      authed.value = !!a
    } catch {
      authed.value = false
    } finally {
      ready.value = true
    }
  }

  async function login(password) {
    await apiLogin(password)
    authed.value = true
  }

  async function logout() {
    try {
      await apiLogout()
    } finally {
      authed.value = false
    }
  }

  return { authed, ready, checkSession, login, logout }
}
```

- [ ] **Step 2: Create `frontend/src/components/LoginView.vue`**

```vue
<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuth } from '../composables/useAuth'

const { login } = useAuth()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  if (!password.value) {
    error.value = '请输入密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await login(password.value)
    ElMessage.success('登录成功')
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">🎬 SeeDance 登录</h2>
      <el-input
        v-model="password"
        type="password"
        placeholder="管理员密码"
        show-password
        size="large"
        @keyup.enter="onSubmit"
      />
      <p v-if="error" class="err">{{ error }}</p>
      <el-button type="primary" size="large" :loading="loading" class="btn" @click="onSubmit">
        登录
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}
.login-card {
  width: 360px;
}
.title {
  text-align: center;
  margin: 0 0 20px;
}
.btn {
  width: 100%;
  margin-top: 16px;
}
.err {
  color: #f56c6c;
  font-size: 13px;
  margin: 8px 0 0;
}
</style>
```

- [ ] **Step 3: Edit `frontend/src/App.vue` script — add imports, auth state, mounted gate**

Change the first import line (currently line 2) to add `onMounted`:

```javascript
import { ref, computed, onUnmounted, onMounted } from 'vue'
```

Add these imports after the existing `HistoryList` import (line 6):

```javascript
import LoginView from './components/LoginView.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { useAuth } from './composables/useAuth'
```

Add after `const { history, add, update, remove, clear } = useHistory()` (line 10):

```javascript
const { authed, ready, checkSession, logout } = useAuth()
const showSettings = ref(false)
```

Remove the top-level history-restore block (currently lines 119-122):

```javascript
// 页面加载/刷新时，为历史里所有未完成任务自动恢复并行轮询
history.value.forEach((h) => {
  if (!isTerminal(h.status)) startPolling(h.taskId)
})
```

Replace it with an on-mount gate that only resumes polling after auth is confirmed:

```javascript
// 先确认会话，登录后再恢复历史中未完成任务的轮询
onMounted(async () => {
  await checkSession()
  if (authed.value) {
    history.value.forEach((h) => {
      if (!isTerminal(h.status)) startPolling(h.taskId)
    })
  }
})
```

(Leave `onUnmounted(stopAll)` on the following line as-is.)

- [ ] **Step 4: Edit `frontend/src/App.vue` template — gate + header buttons + dialog**

Replace the entire `<template>...</template>` block with:

```vue
<template>
  <LoginView v-if="ready && !authed" />

  <el-container v-else-if="ready && authed" class="app">
    <el-header class="header">
      <span class="logo">🎬 SeeDance 视频生成测试台</span>
      <span class="sub">输入提示词，测试 dreamina-seedance 视频生成（多任务并行）</span>
      <span class="spacer" />
      <el-button text @click="showSettings = true">⚙️ 设置</el-button>
      <el-button text @click="logout">退出登录</el-button>
    </el-header>

    <el-main>
      <div class="grid">
        <div class="left">
          <GenerateForm :loading="loading" @submit="onSubmit" />
        </div>
        <div class="middle">
          <ResultPanel
            :task-id="current?.taskId || ''"
            :status="current?.status || ''"
            :progress="current?.progress"
            :video-url="current?.videoUrl || ''"
            :message="current?.message || ''"
            :submit-error="submitError"
            :poll-error="current?.pollError || ''"
          />
        </div>
        <div class="right">
          <HistoryList
            :history="history"
            :active-id="selectedId"
            @select="onSelect"
            @remove="onRemove"
            @clear="onClear"
          />
        </div>
      </div>
    </el-main>

    <SettingsDialog v-model="showSettings" />
  </el-container>
</template>
```

Add one rule to the `<style scoped>` block (after the `.sub` rule, ~line 181):

```css
.spacer {
  flex: 1;
}
```

- [ ] **Step 5: Build to verify (SettingsDialog created in Task 7 — do Task 7 Step 1 first for a green build)**

Run: `cd frontend && npm run build`
Expected: build succeeds once `SettingsDialog.vue` exists. Tasks 6 and 7 are one logical unit; if you want a green build at this commit, create `SettingsDialog.vue` (Task 7 Step 1) before running this build.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/composables/useAuth.js frontend/src/components/LoginView.vue frontend/src/App.vue
git commit -m "feat(frontend): auth composable, login view, gate app behind login"
```

---

### Task 7: Settings dialog + end-to-end manual verification

**Files:**
- Create: `frontend/src/components/SettingsDialog.vue`

**Interfaces:**
- Consumes: `getSettings`, `saveSettings`, `fetchOptions` from `../api` (Task 5); `v-model` (`modelValue` boolean) from `App.vue` (Task 6).
- Produces: a dialog that shows the masked current key + source, lets the admin set a new API_KEY and API_BASE, saves via `PUT /api/settings`, and offers a "测试连接" check.

- [ ] **Step 1: Create `frontend/src/components/SettingsDialog.vue`**

```vue
<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getSettings, saveSettings, fetchOptions } from '../api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const info = ref({ api_key_masked: '', api_key_source: 'unset', api_base: '' })
const newKey = ref('')
const apiBase = ref('')

const SOURCE_LABEL = { file: '文件', env: '环境变量', unset: '未配置' }

async function load() {
  loading.value = true
  try {
    info.value = await getSettings()
    apiBase.value = info.value.api_base || ''
    newKey.value = ''
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load()
  }
)

async function onSave() {
  saving.value = true
  try {
    const payload = { api_base: apiBase.value }
    if (newKey.value.trim()) payload.api_key = newKey.value.trim()
    info.value = await saveSettings(payload)
    apiBase.value = info.value.api_base || ''
    newKey.value = ''
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function onTest() {
  testing.value = true
  try {
    await fetchOptions()
    ElMessage.success('连接正常')
  } catch (e) {
    ElMessage.error('连接失败：' + e.message)
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="设置"
    width="480px"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <el-form v-loading="loading" label-width="90px">
      <el-form-item label="当前 Key">
        <span>{{ info.api_key_masked || '（未配置）' }}</span>
        <el-tag size="small" style="margin-left: 8px">{{ SOURCE_LABEL[info.api_key_source] }}</el-tag>
      </el-form-item>
      <el-form-item label="新 API_KEY">
        <el-input v-model="newKey" type="password" show-password placeholder="留空则不修改" />
      </el-form-item>
      <el-form-item label="API_BASE">
        <el-input v-model="apiBase" placeholder="https://token.manateeai.com" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :loading="testing" @click="onTest">测试连接</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 2: Build the frontend**

Run: `cd frontend && npm run build`
Expected: PASS (no missing imports; `dist/` produced).

- [ ] **Step 3: Run the backend and capture the admin password**

Run (from `backend/`, with a fresh/empty `../data`): `cd backend && python -m uvicorn app:app --reload --port 8008`
Expected: console prints a boxed `ADMIN PASSWORD (save this): <pw>` on first run. Copy `<pw>`.

- [ ] **Step 4: Run the frontend dev server and verify end-to-end**

Run (separate terminal): `cd frontend && npm run dev`
Then at `http://localhost:5173`, verify each:
1. The app shows the **login screen** (not the generator grid).
2. Wrong password → inline "密码错误"; correct `<pw>` → grid appears.
3. Click **⚙️ 设置** → dialog shows source "未配置" (or "环境变量"); enter an API_KEY, Save → toast "已保存"; reopen shows masked `sk-…` with source "文件".
4. **测试连接** → "连接正常" when a valid key is set.
5. Submitting a prompt with no key configured → error "请先在设置中配置 API_KEY".
6. Click **退出登录** → returns to login screen; reloading the page stays logged out.

- [ ] **Step 5: Run the full backend test suite once more**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS (all tests green).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SettingsDialog.vue
git commit -m "feat(frontend): settings dialog for API key/base configuration"
```

(If the built `frontend/dist` is tracked in this repo, also rebuild and `git add frontend/dist` before committing so the served bundle matches the source.)

---

### Task 8: Persistence hygiene — ignore files, Docker volume, README

**Files:**
- Modify: `.gitignore`
- Modify: `.dockerignore`
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:** No code interfaces. Deliverable: `data/` is never committed/copied into the image, persists across container rebuilds, and the README documents first-run login + key configuration.

- [ ] **Step 1: Ignore the `data/` directory**

Append `data/` to `.gitignore` (new line after `*.pyc`):

```
data/
```

Append `data/` to `.dockerignore` (new line):

```
data/
```

- [ ] **Step 2: Add a named volume for `data/` in `docker-compose.yml`**

Add a `volumes:` block to the service (after the `environment:` list, replacing the standalone `restart:` line), and a top-level `volumes:` key:

```yaml
    volumes:
      - seedance-data:/app/data
    restart: unless-stopped

volumes:
  seedance-data:
```

(The service already maps port 8000 and injects `SEEDANCE_API_KEY`; the env var remains a valid bootstrap default that the file-configured key overrides.)

- [ ] **Step 3: Document login + key configuration in `README.md`**

Add this section near the run/deploy instructions:

```markdown
## 登录与密钥配置

- **首次启动**：后端会自动生成管理员密码并打印到控制台，形如
  `ADMIN PASSWORD (save this): xxxxx`。请妥善保存——它只在首次生成时显示一次。
  哈希存储在 `data/admin.json`（已 gitignore）。
- **登录**：打开页面后先输入该密码登录，整个应用都在登录之后。
- **配置 API_KEY**：登录后点击右上角 **⚙️ 设置**，填入 API_KEY（可选 API_BASE）并保存。
  值写入 `data/settings.json`，重启后仍生效；未配置时回退到环境变量 `SEEDANCE_API_KEY`。
- **持久化**：Docker 部署已将 `data/` 挂载为命名卷 `seedance-data`，
  重建容器后管理员密码与已配置的 key 均保留。
- **重置管理员密码**：删除 `data/admin.json` 后重启，会重新生成并打印新密码。
```

- [ ] **Step 4: Verify the Docker image builds**

Run: `docker compose build`
Expected: build succeeds. (If Docker is unavailable in this environment, skip and note it — the compose/Dockerfile changes are config-only and covered by the README.)

- [ ] **Step 5: Commit**

```bash
git add .gitignore .dockerignore docker-compose.yml README.md
git commit -m "chore: gitignore/dockerignore data, mount data volume, document login"
```

---

## Notes on execution order

- Tasks 1-4 (backend) are strictly TDD and independently testable via `pytest`.
- Tasks 5-7 (frontend) form one logical unit: `api.js` → `useAuth`/`LoginView`/gate → `SettingsDialog`. For a green `npm run build` at each commit, it's fine to create `SettingsDialog.vue` (Task 7 Step 1) before running the Task 6 build check; the plan calls this out in Task 6 Step 5 and Task 5 Step 2.
- Task 8 is config/docs only.

## CORS note

The existing `CORSMiddleware(allow_origins=["*"])` is unchanged. Credentialed cookie requests work because dev traffic is same-origin through the Vite proxy (`/api` → `127.0.0.1:8008`) and production is same-origin (FastAPI serves the SPA). No cross-origin credentialed requests occur, so the `"*"` origin is not a problem here.
