ARG PYTHON_BASE_IMAGE=langgenius/dify-api:1.11.4
FROM ${PYTHON_BASE_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1

# 本地 E2E 优先复用机器上已有的 Python 镜像，减少 Docker Hub 拉取失败对验证链路的影响。
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENTRYPOINT []
WORKDIR /workbench

COPY agent-workbench /workbench/agent-workbench
ENV PYTHONPATH=/workbench/agent-workbench
USER root
RUN uv pip install --python /app/api/.venv/bin/python --no-cache -r /workbench/agent-workbench/athena_worker/requirements.txt
RUN npm install -g \
    @anthropic-ai/claude-code@2.1.185 \
    @agentclientprotocol/claude-agent-acp@0.48.0 \
    acpx@0.11.0
USER dify

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
