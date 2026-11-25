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

def show(title, r):
    print("\n### " + title + "  status=" + str(r.get("status")))
    text = "".join(c.get("text", "") for c in r.get("content", []))
    print(text[:1500].encode("ascii", "replace").decode())

with client:
    show("datetime", client.call_tool_sync(
        "t1", "get_current_datetime", {"timezone_name": "America/Bogota"}))
    show("rango", client.call_tool_sync(
        "t2", "get_weather_byDateTimeRange",
        {"city": "Cartagena", "start_date": "2026-11-26", "end_date": "2026-11-29"}))