FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Clone ContextOS (serve/MCP command lives here, not yet on PyPI)
RUN git clone https://github.com/Rohithmatham12/ContextOS.git /tmp/contextos-src --depth=1

# Install from local clone — avoids pip git+https:// tty issues in Docker
RUN pip install --no-cache-dir "/tmp/contextos-src[mcp]"

# Reuse the clone as the demo repo so we don't clone twice
RUN cp -r /tmp/contextos-src /opt/demo-repo

COPY . .

ENV REPO_PATH=/opt/demo-repo
ENV CONTEXTOS_BIN=contextos

CMD ["python", "bot.py"]
