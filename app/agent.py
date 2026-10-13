from __future__ import annotations

import json
from typing import Any, Callable

from app.llm import get_client
from app.mcp_tools import MCP_TOOLS, call_mcp_tool
from app.settings import AGENT_MODEL
from app.tools.calculator import calculate
from app.tools.weather import get_weather

TOOLS = [
    {"type": "function", "function": {"name": "get_weather", "description": "Get deterministic offline demo weather for a city.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "calculate", "description": "Evaluate a basic arithmetic expression.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"], "additionalProperties": False}}},
]
TOOLS.extend(MCP_TOOLS)
_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {"get_weather": get_weather, "calculate": calculate}


def run_agent(prompt: str, max_steps: int = 4) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "Use tools when needed. Weather is deterministic offline demo data. Never invent a tool result."},
        {"role": "user", "content": prompt},
    ]
    trace: list[dict[str, Any]] = []
    for step in range(1, max_steps + 1):
        response = get_client().chat.completions.create(
            model=AGENT_MODEL, messages=messages, tools=TOOLS, tool_choice="auto", temperature=0
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            return {"answer": message.content or "", "steps": trace}
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
                function = _FUNCTIONS.get(name)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be an object")
                if name in {"list_demo_documents", "get_demo_stack_status"}:
                    result: dict[str, Any] = call_mcp_tool(name, arguments)
                elif function is not None:
                    result = function(**arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as exc:
                arguments = {"raw": tool_call.function.arguments}
                result = {"error": str(exc)}
            trace.append({"step": step, "tool": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": name, "content": json.dumps(result)})
    return {"answer": "The agent reached its tool-step limit.", "steps": trace}
