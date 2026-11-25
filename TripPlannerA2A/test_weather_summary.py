import sys, json
sys.path.insert(0, r"C:\agent\TripPlannerA2A\app\WeatherAgent")
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands.tools.mcp import MCPClient
from forecast import summarize

client = MCPClient(
    lambda: stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", "open_meteo_mcp"])
    ),
    startup_timeout=30,
)

with client:
    for city in ["Cartagena", "Bogota"]:
        r = client.call_tool_sync(
            "t", "get_weather_byDateTimeRange",
            {"city": city, "start_date": "2026-11-26", "end_date": "2026-11-29"},
        )
        text = "".join(c.get("text", "") for c in r.get("content", []))
        print("\n###", city, "- largo del texto:", len(text))
        print(json.dumps(summarize(text), indent=1).encode("ascii", "replace").decode())