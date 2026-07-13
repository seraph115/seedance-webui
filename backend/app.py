"""FastAPI 中转服务。

职责：
- 隐藏 API Key、解决浏览器跨域
- 3 个接口：提交任务 / 查询状态 / 列出可选模型
- 生产模式下托管前端构建产物（frontend/dist）

运行：
    uvicorn app:app --reload --port 8000
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import seedance

app = FastAPI(title="SeeDance 视频生成测试台")

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


@app.get("/api/models")
def list_models():
    """返回可选模型与参数枚举，供前端下拉。"""
    return {
        "models": config.MODELS,
        "resolutions": ["480p", "720p", "1080p"],
        "durations": [5, 10],
    }


@app.post("/api/generate")
def generate(req: GenerateRequest):
    """提交生成任务，返回 task_id。"""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt 不能为空")
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


@app.get("/api/status/{task_id}")
def status(task_id: str):
    """单次查询任务状态。"""
    try:
        return seedance.query(task_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询失败：{e}")


# ---- 托管前端构建产物（存在时才挂载，开发阶段没有 dist 也不影响 API）----
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
