from mcp.client.streamable_http import streamable_http_client
from strands.tools.mcp import MCPClient

URL = "https://mcp.kiwi.com"

client = MCPClient(lambda: streamable_http_client(URL))

with client:
    tools = client.list_tools_sync()
    for t in tools:
        print(t.tool_name)
