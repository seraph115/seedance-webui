"""封装对 SeeDance（token.manateeai.com）视频生成接口的调用。

从原脚本 seedance-token-prod(1).py 重构而来：
- build_payload : 按模式组装请求体
- submit        : 提交生成任务，返回 task_id
- query         : 单次查询任务状态，归一化返回结构

不做阻塞式 while 轮询——轮询交给前端，后端每次只查一次。
"""
import requests

import config


def build_payload(
    *,
    mode: str,
    prompt: str,
    duration: int = 5,
    resolution: str = "720p",
    model: str | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    images: list[str] | None = None,
) -> dict:
    """按 mode 组装请求体。

    mode:
      - "text"  文生视频：仅 prompt + 基础参数
      - "image" 图生视频/首尾帧：可带 first_frame/last_frame(URL) 和 images(asset id)
    """
    metadata: dict = {"duration": duration, "resolution": resolution}

    if mode == "image":
        if first_frame:
            metadata["first_frame"] = first_frame
        if last_frame:
            metadata["last_frame"] = last_frame

    payload: dict = {
        "model": model or config.MODELS[0],
        "prompt": prompt,
        "metadata": metadata,
    }

    if mode == "image" and images:
        payload["images"] = images

    return payload


def submit(payload: dict) -> dict:
    """提交生成任务。成功返回 {"task_id": ...}，失败抛出携带上游可读信息的异常。"""
    url = f"{config.API_BASE}/v1/video/generations"
    resp = requests.post(
        url,
        json=payload,
        headers=_headers(),
        timeout=config.REQUEST_TIMEOUT,
    )
    # 上游 4xx/5xx：把响应体带出来（真正的模型报错通常在 body 里）
    if resp.status_code >= 400:
        raise RuntimeError(f"上游返回 HTTP {resp.status_code}：{_short(resp.text)}")

    data = resp.json()
    task_id = data.get("task_id")
    if not task_id:
        # HTTP 200 但业务失败（如 code != success）：带出可读信息
        msg = data.get("message") or data.get("error") or data
        raise ValueError(f"提交未返回 task_id：{_short(str(msg))}")
    return {"task_id": task_id, "raw": data}


def query(task_id: str) -> dict:
    """单次查询任务状态，归一化为统一结构。

    返回：
      {
        "status": "SUCCESS" | "IN_PROGRESS" | "FAILURE" | "UNKNOWN",
        "progress": <int|None>,
        "video_url": <str|None>,
        "message": <str|None>,
        "raw": <原始响应>,
      }
    """
    url = f"{config.API_BASE}/v1/video/generations/{task_id}"
    resp = requests.get(url, headers=_headers(), timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    res = resp.json()

    data = res.get("data") or {}
    status = data.get("status", "UNKNOWN")

    return {
        "status": status,
        "progress": data.get("progress"),
        "video_url": _extract_video_url(res) if status == "SUCCESS" else None,
        "message": _extract_message(res),
        "raw": res,
    }


def _short(text: str, limit: int = 500) -> str:
    """截断过长文本，避免把整段响应体塞进错误信息。"""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _extract_message(res: dict) -> str:
    """提取可读的状态/失败信息：优先 fail_reason（外层/内层），回退顶层 message。"""
    data = res.get("data") or {}
    inner = (data.get("data") or {}).get("data") or {}
    for m in (data.get("fail_reason"), inner.get("fail_reason"), res.get("message")):
        if m:
            return str(m)
    return ""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.API_KEY}",
        "Content-Type": "application/json",
    }


def _extract_video_url(res: dict) -> str | None:
    """从可能变化的嵌套结构里提取视频地址。

    对应原脚本里的四层兜底：
      data.data.data.data.content.video_url  →  否则 data.result_url
    """
    data = res.get("data") or {}
    try:
        return data["data"]["data"]["data"]["content"]["video_url"]
    except (KeyError, TypeError):
        return data.get("result_url")
