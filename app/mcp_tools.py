"""Bounded stdio adapter to the demo's declared MCP tools."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
DECLARED_TOOLS = {
    "list_demo_documents": "List available local demo document names via MCP.",
    "get_demo_stack_status": "Describe the local demo stack components via MCP (not a live health check).",
}
MCP_TOOLS = [
    {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}
    for name, description in DECLARED_TOOLS.items()
]


async def _call(name: str) -> dict[str, Any]:
    command = os.getenv("DEMO_MCP_PYTHON", sys.executable)
    params = StdioServerParameters(command=command, args=["-m", "mcp_servers.demo"], cwd=ROOT)
    async with asyncio.timeout(10):
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments={})
                if result.isError:
                    raise RuntimeError("MCP server returned a tool error")
                return result.structuredContent or {"content": [item.text for item in result.content if item.type == "text"]}


def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in DECLARED_TOOLS or arguments:
        raise ValueError("MCP tool unavailable or unexpected arguments")
    try:
        return asyncio.run(_call(name))
    except (Exception, ExceptionGroup) as exc:
        raise RuntimeError("Demo MCP server unavailable or timed out") from exc
