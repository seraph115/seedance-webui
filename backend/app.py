"""FastAPI 中转服务。

职责：
- 隐藏 API Key、解决浏览器跨域
- 3 个接口：提交任务 / 查询状态 / 列出可选模型
- 生产模式下托管前端构建产物（frontend/dist）

运行：
    uvicorn app:app --reload --port 8000
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import seedance

from starlette.middleware.sessions import SessionMiddleware

import auth
import settings_store

app = FastAPI(title="SeeDance 视频生成测试台")

# 首次启动生成并打印 admin 密码（仅一次），并装配签名 Cookie 会话
_first_run_pw = auth.ensure_admin()
if _first_run_pw:
    auth.announce_password(_first_run_pw)  # Task 1 提供的公共打印助手，保持 DRY

app.add_middleware(
    SessionMiddleware,
    secret_key=auth.get_secret_key(),
    same_site="lax",
    https_only=False,
)

# 开发时前端跑在 Vite(5173)，允许跨域；生产同源则无所谓
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    mode: str = Field("text", description="text 文生视频 / image 图生视频")
    prompt: str
    duration: int = 5
    resolution: str = "720p"
    model: str | None = None
    first_frame: str | None = None
    last_frame: str | None = None
    images: list[str] | None = None


class LoginRequest(BaseModel):
    password: str


class SettingsRequest(BaseModel):
    api_key: str | None = None
    api_base: str | None = None


@app.get("/api/models", dependencies=[Depends(auth.require_auth)])
def list_models():
    """返回可选模型与参数枚举，供前端下拉。"""
    return {
        "models": config.MODELS,
        "resolutions": ["480p", "720p", "1080p"],
        "durations": [5, 10],
    }


@app.post("/api/generate", dependencies=[Depends(auth.require_auth)])
def generate(req: GenerateRequest):
    """提交生成任务，返回 task_id。"""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt 不能为空")
    if not settings_store.get_api_key():
        raise HTTPException(status_code=400, detail="请先在设置中配置 API_KEY")
    payload = seedance.build_payload(
        mode=req.mode,
        prompt=req.prompt,
        duration=req.duration,
        resolution=req.resolution,
        model=req.model,
        first_frame=req.first_frame,
        last_frame=req.last_frame,
        images=req.images,
    )
    try:
        result = seedance.submit(payload)
    except Exception as e:  # 网络错误 / 未返回 task_id 等
        raise HTTPException(status_code=502, detail=f"提交失败：{e}")
    return {"task_id": result["task_id"], "payload": payload}


@app.get("/api/status/{task_id}", dependencies=[Depends(auth.require_auth)])
def status(task_id: str):
    """单次查询任务状态。"""
    try:
        return seedance.query(task_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询失败：{e}")


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


# ---- 托管前端构建产物（存在时才挂载，开发阶段没有 dist 也不影响 API）----
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
