import sys, json
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
    for t in client.list_tools_sync():
        spec = t.tool_spec
        props = list(spec.get("inputSchema", {}).get("json", {}).get("properties", {}).keys())
        print(t.tool_name, "->", props)
        print("   ", spec.get("description", "")[:200].replace("\n", " ").encode("ascii", "replace").decode())