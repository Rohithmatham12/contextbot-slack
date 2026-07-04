FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ContextOS with MCP support from source (has serve command)
RUN pip install --no-cache-dir "git+https://github.com/Rohithmatam12/ContextOS.git#egg=rm-contextos[mcp]"

# Clone ContextOS repo as the demo repo to scan
RUN git clone https://github.com/Rohithmatam12/ContextOS /opt/demo-repo --depth=1

COPY . .

ENV REPO_PATH=/opt/demo-repo
ENV CONTEXTOS_BIN=contextos

CMD ["python", "bot.py"]
