"""Small smoke-test client: discovers MCP tools and checks read-only operations."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def print_tool_result(label, result):
    print(f"\n{label}:")
    if result.is_error:
        print("Tool execution failed.")
        for block in result.content:
            if isinstance(block, TextContent):
                print(block.text)
        return
    if result.structured_content is not None:
        print(json.dumps(result.structured_content, indent=2, ensure_ascii=False))
        return
    for block in result.content:
        if isinstance(block, TextContent):
            try:
                print(json.dumps(json.loads(block.text), indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(block.text)


async def main():
    params = StdioServerParameters(
        command=PYTHON,
        args=["-m", "app.mcp_server.server"],
        cwd=str(PROJECT_ROOT),
    )
    async with Client(params) as client:
        tools_result = await client.list_tools()
        print("\nAvailable MCP tools:")
        for tool in tools_result.tools:
            print(f"- {tool.name}: {tool.description}")

        summary = await client.call_tool("get_financial_summary", {})
        print_tool_result("Financial summary", summary)

        upcoming = await client.call_tool("get_upcoming_bills", {"limit": 2})
        print_tool_result("Upcoming unpaid bills", upcoming)

        catalogue = await client.call_tool("list_investment_products", {})
        print_tool_result("Investment catalogue", catalogue)


if __name__ == "__main__":
    asyncio.run(main())
