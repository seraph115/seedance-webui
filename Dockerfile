# syntax=docker/dockerfile:1

# ============ Stage 1：构建前端 ============
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
# 先装依赖（利用缓存层）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# 再拷源码并构建，产出 /app/frontend/dist
COPY frontend/ ./
RUN npm run build

# ============ Stage 2：后端运行时 ============
FROM python:3.11-slim AS runtime
WORKDIR /app/backend

# 安装后端依赖
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端源码
COPY backend/ ./

# 拷贝前端构建产物到 app.py 期望的位置：<项目根>/frontend/dist
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# 默认配置（密钥不写入镜像，运行时用 -e SEEDANCE_API_KEY 注入）
ENV SEEDANCE_API_BASE=https://token.manateeai.com \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# FastAPI 同源托管前端(/) 与 API(/api/*)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
