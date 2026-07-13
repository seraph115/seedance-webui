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
