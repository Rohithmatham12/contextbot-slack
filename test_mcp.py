"""Quick smoke test — run this before starting the bot."""
import os
import sys

# Point at the ContextOS repo itself as demo
os.environ.setdefault("REPO_PATH", "/Users/rohithmatam/ContextOS")
os.environ.setdefault("CONTEXTOS_BIN", str(
    __import__("pathlib").Path(__file__).parent / ".venv/bin/contextos"
))

import mcp_client

print("Testing scan_repo...")
result = mcp_client.scan_repo()
print(result[:300])
print("\n---\nTesting list_files...")
result = mcp_client.list_files("how does context packing work", top_n=5)
print(result[:400])
print("\nMCP client OK ✓")
