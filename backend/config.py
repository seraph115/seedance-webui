"""运行配置：API 地址与密钥。

密钥只从环境变量 SEEDANCE_API_KEY 读取，不在源码中内置任何默认值。
运行前请通过环境变量或 .env 设置密钥。
"""
import os

# 中转服务地址
API_BASE = os.getenv("SEEDANCE_API_BASE", "https://token.manateeai.com")

# 鉴权密钥：必须通过环境变量 SEEDANCE_API_KEY 提供（未设置则为空，调用会返回鉴权错误）
API_KEY = os.getenv("SEEDANCE_API_KEY", "")

# 可用模型列表（供前端下拉展示）
MODELS = [
    "dreamina-seedance-2-0-hc",
    "dreamina-seedance-2-0-fast-hc",
]

# 请求超时（秒）
REQUEST_TIMEOUT = int(os.getenv("SEEDANCE_TIMEOUT", "180"))
