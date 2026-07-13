# SeeDance 视频生成测试台

一个用于**测试提示词生成视频**的小工具：FastAPI 后端中转 + Vue3 前端。
基于原脚本 `seedance-token-prod(1).py` 的 API 逻辑重构而来。

## 功能

- 📝 **文生视频**：输入提示词直接生成
- 🎛️ **参数可调**：时长、分辨率、模型下拉可选
- 🖼️ **图生视频 / 首尾帧**：支持 `first_frame`/`last_frame`（公网图片 URL）与 `images`（asset id）
- 🕘 **历史记录**：浏览器本地保存每次的提示词、task_id 与视频地址，可回看

## 目录结构

```
seedance-webui/
├── backend/            # FastAPI 中转服务
│   ├── app.py          #   3个接口 + 托管前端产物
│   ├── seedance.py     #   封装提交/查询（重构自原脚本）
│   ├── config.py       #   API 地址与密钥（读环境变量）
│   └── requirements.txt
├── frontend/           # Vue3 + Vite + Element Plus
│   └── src/
│       ├── App.vue     #   主逻辑：提交 + 前端轮询
│       ├── api.js      #   axios 封装
│       ├── components/ #   GenerateForm / ResultPanel / HistoryList
│       └── composables/useHistory.js
├── .env.example
└── README.md
```

## 快速开始

### 1. 启动后端（终端 A）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 设置密钥（也可 cp ../.env.example ../.env 后 export）
export SEEDANCE_API_KEY=sk-你的密钥

uvicorn app:app --reload --port 8000
```

后端起在 `http://127.0.0.1:8000`，接口文档见 `http://127.0.0.1:8000/docs`。

### 2. 启动前端（终端 B）

```bash
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173` 即可使用。开发模式下 Vite 会把 `/api` 代理到后端 8000，无需关心跨域。

### 3. 生产部署（可选：单服务）

```bash
cd frontend && npm run build      # 产出 frontend/dist
cd ../backend && uvicorn app:app --port 8000
```

此时后端会自动托管 `frontend/dist`，直接访问 `http://127.0.0.1:8000` 即可，前后端同源。

## Docker 部署（推荐）

工程已做成**单镜像、单端口**：多阶段构建里 Node 先编译前端，再由 Python 后端同源托管前端(`/`)和 API(`/api/*`)。镜像约 286MB，密钥不写入镜像、运行时注入。

### 方式一：docker build + run

```bash
cd seedance-webui
docker build -t seedance-webui:latest .

docker run -d --name seedance-webui \
  -p 8000:8000 \
  -e SEEDANCE_API_KEY=sk-你的密钥 \
  seedance-webui:latest
```

打开 `http://localhost:8000` 即可（前后端同源，无需单独起前端）。

### 方式二：docker compose

```bash
cd seedance-webui
export SEEDANCE_API_KEY=sk-你的密钥   # 或写进同目录 .env 文件
docker compose up -d --build
```

### 运行时环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SEEDANCE_API_KEY` | 无（必填） | **必须设置为你自己的密钥**，否则调用返回鉴权错误 |
| `SEEDANCE_API_BASE` | `https://token.manateeai.com` | 中转地址 |
| `SEEDANCE_TIMEOUT` | `180` | 请求超时（秒） |

> 端口冲突时改左侧映射即可，如 `-p 18080:8000`，再访问 `http://localhost:18080`。

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
- 若通过 HTTPS 部署，可设置 `SEEDANCE_HTTPS_ONLY=1` 让登录会话 Cookie 带上 `Secure` 标记。
- **单进程运行**：管理员凭据与会话签名密钥在进程内首次启动时生成，登录限流也是进程内状态。请勿在没有外部会话/密钥存储的情况下用多 worker（如 `uvicorn --workers N`）启动，否则各 worker 可能生成不一致的密钥导致偶发 401。默认镜像为单 worker，无需担心。

## 接口说明

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/models` | 返回可选模型与参数枚举 |
| POST | `/api/generate` | 提交生成任务，返回 `task_id` |
| GET | `/api/status/{task_id}` | 单次查询任务状态 |

前端每 5 秒轮询一次 `/api/status`，状态为 `SUCCESS` 时渲染视频播放器。

## 已知限制

- 图生视频的 `images` 需要 `asset://asset-xxxx` 素材 ID，**本地图片上传接口未包含在原脚本中**，界面保留手动填入；首尾帧走公网 URL 可直接使用。
- API Key **不内置在源码中**，必须通过 `SEEDANCE_API_KEY` 环境变量（或 `.env`）提供。
