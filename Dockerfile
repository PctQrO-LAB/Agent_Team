# 1. 选择最轻量的 Python 官方镜像 (Debian Bookworm Slim 版本)
# 体积极小，仅包含最小运行环境
FROM python:3.11-slim

# 2. 设置环境变量
# 避免生成 .pyc 垃圾文件
ENV PYTHONDONTWRITEBYTECODE=1
# 让日志即时输出，方便 docker logs 查看
ENV PYTHONUNBUFFERED=1

# 设置容器内工作目录
WORKDIR /app

# === 网络代理设置 (可选) ===
# 如果你的 NAS 下载 pip 包很慢或连不上，请取消注释并修改 IP
# ENV http_proxy=http://192.168.1.5:7890
# ENV https_proxy=http://192.168.1.5:7890

# 3. 安装最小系统依赖
# 移除了 Java，仅保留 git (防止某些 pip 包安装需要)
# 并在同一层清理 apt 缓存，最大化减小体积
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 4. 安装 Python 依赖
# 利用 Docker 分层缓存机制：先拷 requirements，后拷代码
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 拷贝源代码
COPY . .

# 6. 启动命令
CMD ["python", "src/launch.py"]