# Design: Admin Login + Page-Configured API_KEY

Date: 2026-07-14
Project: seedance-webui
Status: Approved (ready for implementation planning)

## Summary

Add two capabilities to the SeeDance WebUI:

1. **Admin login** — the entire application is placed behind a single-admin login. A strong
   admin password is auto-generated on first backend startup and printed to the console; only
   its salted hash is persisted.
2. **Page-configured API_KEY** — the upstream API key (and optionally API base URL) can be
   configured from a Settings panel in the UI instead of only via environment variable. The
   configured value is persisted to a local file and takes effect without a restart.

## Context (current state)

- **Backend** (FastAPI): `config.py` reads `API_KEY`/`API_BASE` from env at import time;
  `seedance.py` builds `Authorization: Bearer {config.API_KEY}` headers; `app.py` exposes
  `/api/models`, `/api/generate`, `/api/status/{id}` and serves the built frontend. No auth,
  no database, no server-side persistence today.
- **Frontend** (Vue 3 + Element Plus): single `App.vue`, **no router**, no login. History is
  kept in browser `localStorage` via `composables/useHistory.js`.
- **Deploy**: single Docker container serving both API and static frontend.

## Decisions (locked)

| Decision | Choice |
| --- | --- |
| Login scope | Entire app behind login; single `admin` account |
| Password lifecycle | Auto-generated on first startup, printed to console once; only salted hash stored |
| Password hashing | PBKDF2-HMAC-SHA256 (stdlib `hashlib`), per-credential random salt, high iteration count — no new dependency |
| API_KEY storage | Written to local file `data/settings.json`; env `SEEDANCE_API_KEY` is the default/fallback |
| Session mechanism | HttpOnly signed cookie via Starlette `SessionMiddleware` (adds `itsdangerous`) |
| Frontend gate | Conditional render via a `useAuth` composable (no vue-router added) |
| API_BASE editable in UI | Yes — same Settings panel, optional field |
| Password change from UI | Out of scope for v1 (rotate by deleting `data/admin.json` + restart) |

## Architecture

### Backend

**`backend/auth.py` (new)** — credentials + session helpers
- On startup, ensure an admin credential file `data/admin.json` exists. If absent:
  - Generate a strong random password (e.g. `secrets.token_urlsafe(15)` → ~20 chars).
  - **Print it once** to the console/log (clearly marked, e.g. `ADMIN PASSWORD (save this): <pw>`).
  - Store `{ "salt": <hex>, "hash": <hex>, "iterations": <int>, "secret_key": <hex> }` to
    `data/admin.json`. The plaintext password is never written to disk.
- `verify_password(pw: str) -> bool` — recompute PBKDF2 with stored salt/iterations and compare
  using `hmac.compare_digest`.
- `get_secret_key() -> str` — the persisted cookie-signing secret (generated once, stored in
  `data/admin.json`).
- `require_auth` — a FastAPI dependency that returns 401 unless `request.session.get("authed")`
  is true.
- Light brute-force throttle for login attempts (in-memory): small fixed delay on failure and a
  temporary lockout after N consecutive failures. Reset on success. (Practical safety net; the
  random password already makes brute force infeasible.)

**`backend/settings_store.py` (new)** — runtime settings persistence
- Backing file: `data/settings.json` (e.g. `{ "api_key": "...", "api_base": "..." }`).
- `get_api_key() -> str` — return the file value if present and non-empty, else fall back to env
  `SEEDANCE_API_KEY` (via existing `config`).
- `get_api_base() -> str` — file value if set, else env / `config.API_BASE` default.
- `set_settings(api_key: str | None, api_base: str | None) -> None` — merge + write
  `data/settings.json` (only overwrite fields that are provided).
- `describe() -> dict` — `{ "api_key_masked": "sk-…QlT" | "", "api_key_source": "file" | "env" | "unset", "api_base": "..." }`. Never returns the full key.

**`backend/seedance.py` (change)**
- `_headers()` now reads `settings_store.get_api_key()` (live) instead of the import-time
  `config.API_KEY`.
- `submit()`/`query()` build the URL from `settings_store.get_api_base()` instead of
  `config.API_BASE`.
- Net effect: a key saved from the UI takes effect on the next request without a restart.

**`backend/app.py` (change)**
- Add `SessionMiddleware(app, secret_key=auth.get_secret_key(), https_only=False, same_site="lax")`
  → HttpOnly signed cookie by default. (`https_only` can be gated on an env flag for prod.)
- New endpoints:
  - `POST /api/login` `{ "password": str }` → on success set `request.session["authed"] = True`,
    return `{ "ok": true }`; on failure return 401 (throttled).
  - `POST /api/logout` → `request.session.clear()`, return `{ "ok": true }`.
  - `GET /api/session` → `{ "authed": bool }` (unauthenticated; used by the frontend on load).
  - `GET /api/settings` *(require_auth)* → `settings_store.describe()`.
  - `PUT /api/settings` `{ "api_key"?: str, "api_base"?: str }` *(require_auth)* →
    `set_settings(...)`, return the new `describe()`.
- Protect existing endpoints with `require_auth`: `GET /api/models`, `POST /api/generate`,
  `GET /api/status/{task_id}`.
- Static SPA mount stays open (it contains the login screen); all `/api/*` data endpoints are
  protected as above.

### Frontend

**`composables/useAuth.js` (new)**
- `authed` (ref, starts `false`), `ready` (ref, false until first session check completes).
- `checkSession()` → GET `/api/session`, set `authed`.
- `login(password)` → POST `/api/login`; on success set `authed = true`.
- `logout()` → POST `/api/logout`; set `authed = false`.
- Exposed as a module-level singleton so `api.js`'s 401 interceptor can flip `authed` too.

**`components/LoginView.vue` (new)**
- Centered card: single password input + submit button; inline error on 401; loading state.
- Emits nothing external — calls `useAuth().login()` directly.

**`components/SettingsDialog.vue` (new)**
- Opened from a ⚙️ button in the header. On open, GET `/api/settings` to show:
  - masked current key + source label (文件 / 环境变量 / 未配置),
  - an input to set a new API_KEY,
  - an optional input for API_BASE (prefilled with current).
- Save → PUT `/api/settings`; success toast; refresh the masked display.
- Optional “测试连接” button → GET `/api/models`; success/fail toast.

**`App.vue` (change)**
- On mount call `checkSession()`. While `!ready`, render nothing/spinner.
- If `!authed` → render `<LoginView>`. If `authed` → render the existing grid.
- Header gains a ⚙️ Settings button (opens `SettingsDialog`) and a 退出登录 button (calls `logout`).

**`api.js` (change)**
- `axios.create({ baseURL: '/api', withCredentials: true, ... })` so the session cookie is sent.
- Add `login`, `logout`, `getSession`, `getSettings`, `saveSettings`.
- Response interceptor: on HTTP 401, set `useAuth().authed = false` (drop to login) before
  rejecting, so any protected call that fails auth returns the user to the login screen.

## Data flow (first run)

1. Backend boots → no `data/admin.json` → generates password, prints
   `ADMIN PASSWORD (save this): <pw>`, writes salted hash + secret key.
2. Operator copies the password from the log.
3. Opens the app → `checkSession()` returns `{authed:false}` → **LoginView**.
4. Enters password → `POST /api/login` → cookie set → main app renders.
5. Opens **Settings** → pastes API_KEY → `PUT /api/settings` → written to `data/settings.json`.
6. Generates video → backend uses the file-stored key. On restart, the same password (hash) and
   key (file) still apply.

## Error handling

- Wrong password → 401 + inline message; repeated failures throttled/locked briefly.
- API_KEY not configured (file empty and no env) → `/api/generate` returns a clear message,
  e.g. `请先在设置中配置 API_KEY`, surfaced by the existing error-display path.
- Any protected `/api/*` returning 401 (e.g. expired/cleared session) → interceptor flips
  `authed=false` → app returns to LoginView.
- Upstream errors keep their current behavior (HTTP 502 with readable detail).

## Secrets & files hygiene

- New `data/` directory holds `admin.json` (salt, hash, iterations, secret_key) and
  `settings.json` (api_key, api_base).
- Add `data/` to `.gitignore` and `.dockerignore`.
- Docker: document mounting `data/` as a named volume so credentials and the configured key
  persist across container rebuilds. `SEEDANCE_API_KEY` env remains a valid bootstrap/default.
- `requirements.txt`: add `itsdangerous` (required by Starlette `SessionMiddleware`).

## Testing

Backend (`pytest`, using FastAPI `TestClient`):
- Password hash + verify: correct password verifies, wrong password fails.
- `POST /api/login` success sets a session cookie; wrong password → 401.
- Protected endpoint (`/api/models`) → 401 without cookie, 200 with a valid session cookie.
- `PUT /api/settings` then `GET /api/settings` reflects the change (masked); `get_api_key()`
  returns file value when set, else env fallback.
- `/api/generate` with no key configured returns the clear "configure API_KEY" error.

Frontend: manual verification of the login gate, settings save, and 401→login redirect. The repo
has no frontend test setup today; adding one is out of scope for this change.

## Non-goals (v1)

- No password change / reset from the UI (rotate via delete `data/admin.json` + restart).
- No multi-user accounts or roles.
- No "remember me" duration tuning beyond a sensible cookie lifetime.
- No frontend test harness introduction.
