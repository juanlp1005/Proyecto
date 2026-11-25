import sys
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands.tools.mcp import MCPClient

client = MCPClient(
    lambda: stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", "open_meteo_mcp"])
    ),
    startup_timeout=30,
)

with client:
    tools = client.list_tools_sync()
    print("Tools:", [t.tool_name for t in tools])
    r = client.call_tool_sync("t1", "get_current_weather", {"city": "Cartagena"})
    text = r["content"][0]["text"]
    print(text[:500].encode("ascii", "replace").decode())