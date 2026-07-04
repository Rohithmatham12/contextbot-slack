"""ContextOS MCP client — wraps the MCP server in a clean sync API."""
import asyncio
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_PATH = os.getenv("REPO_PATH", ".")

# Use venv binary if present, fall back to PATH
_here = os.path.dirname(__file__)
_venv_bin = os.path.join(_here, ".venv", "bin", "contextos")
CONTEXTOS_BIN = os.getenv(
    "CONTEXTOS_BIN",
    _venv_bin if os.path.isfile(_venv_bin) else "contextos",
)


async def _call(tool: str, args: dict[str, Any]) -> str:
    params = StdioServerParameters(
        command=CONTEXTOS_BIN,
        args=["serve", "--stdio", REPO_PATH],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            if result.content:
                return result.content[0].text  # type: ignore[union-attr]
            return "No result."


def call(tool: str, args: dict[str, Any] | None = None) -> str:
    return asyncio.run(_call(tool, args or {}))


# ── Typed helpers ──────────────────────────────────────────────────────────────

def pack_context(task: str, budget: int = 8000) -> str:
    return call("pack_context", {"task": task, "budget": budget})

def list_files(task: str, top_n: int = 12) -> str:
    return call("list_files", {"task": task, "top_n": top_n})

def scan_repo() -> str:
    return call("scan_repo", {"repo": REPO_PATH})

def get_summary(rel_path: str) -> str:
    return call("get_summary", {"rel_path": rel_path})

def churn_report(days: int = 30, top_n: int = 12) -> str:
    return call("churn_report", {"days": days, "top_n": top_n})
