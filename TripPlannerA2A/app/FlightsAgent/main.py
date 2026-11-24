import os
import logging
from mcp.client.streamable_http import streamable_http_client
from strands import Agent
from strands.tools.mcp import MCPClient
from strands.multiagent.a2a.executor import StrandsA2AExecutor
from bedrock_agentcore.runtime import serve_a2a
from model.load import load_model

logger = logging.getLogger("flights")

TRAVEL_MCP_URL = os.environ.get("TRAVEL_MCP_URL", "https://mcp.kiwi.com")

BASE_PROMPT = (
    "Eres un agente especialista en vuelos. Usa la herramienta search-flight "
    "para buscar vuelos reales. Convierte las ciudades a códigos de aeropuerto "
    "y las fechas al formato que pida la herramienta. Presenta las opciones de "
    "forma clara, con aerolínea, horarios y precio. Si la herramienta falla, "
    "dilo con honestidad en vez de inventar vuelos."
)

FALLBACK_PROMPT = (
    "Eres un agente especialista en vuelos, pero en este momento el servicio "
    "de búsqueda de vuelos no está disponible. Informa al usuario con claridad "
    "que no puedes consultar vuelos ahora y que intente más tarde. "
    "No inventes vuelos, horarios ni precios."
)


def load_travel_tools():
    """Conecta al servidor MCP con timeout. Si falla, devuelve lista vacía."""
    try:
        client = MCPClient(
            lambda: streamable_http_client(TRAVEL_MCP_URL),
            startup_timeout=15,
        )
        client.start()
        tools = [t for t in client.list_tools_sync() if t.tool_name == "search-flight"]
        return client, tools
    except Exception as exc:
        logger.error("MCP no disponible: %s", ascii(exc))
        return None, []


travel_mcp, mcp_tools = load_travel_tools()

agent = Agent(
    name="Flights Agent",
    description="Busca vuelos reales entre ciudades para una fecha dada.",
    model=load_model(),
    system_prompt=BASE_PROMPT if mcp_tools else FALLBACK_PROMPT,
    tools=mcp_tools,
    callback_handler=None,
)

if __name__ == "__main__":
    serve_a2a(StrandsA2AExecutor(agent))