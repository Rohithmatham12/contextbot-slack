"""ContextOS MCP client — per-call repo path support."""
import asyncio
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_here = os.path.dirname(__file__)
_venv_bin = os.path.join(_here, ".venv", "bin", "contextos")
CONTEXTOS_BIN = os.getenv(
    "CONTEXTOS_BIN",
    _venv_bin if os.path.isfile(_venv_bin) else "contextos",
)
DEFAULT_REPO = os.getenv("REPO_PATH", ".")


async def _call(tool: str, args: dict[str, Any], repo_path: str) -> str:
    params = StdioServerParameters(
        command=CONTEXTOS_BIN,
        args=["serve", "--stdio", repo_path],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            if result.content:
                return result.content[0].text  # type: ignore[union-attr]
            return "No result."


def call(tool: str, args: dict[str, Any] | None = None, repo_path: str | None = None) -> str:
    return asyncio.run(_call(tool, args or {}, repo_path or DEFAULT_REPO))


def pack_context(task: str, budget: int = 8000, repo_path: str | None = None) -> str:
    return call("pack_context", {"task": task, "budget": budget}, repo_path)


def list_files(task: str, top_n: int = 12, repo_path: str | None = None) -> str:
    return call("list_files", {"task": task, "top_n": top_n}, repo_path)


def scan_repo(repo_path: str | None = None) -> str:
    return call("scan_repo", {}, repo_path)


def churn_report(days: int = 30, top_n: int = 12, repo_path: str | None = None) -> str:
    return call("churn_report", {"days": days, "top_n": top_n}, repo_path)
