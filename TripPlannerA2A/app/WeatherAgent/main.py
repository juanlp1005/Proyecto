import sys
import logging

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands import Agent
from strands.tools.mcp import MCPClient
from strands.multiagent.a2a.executor import StrandsA2AExecutor
from bedrock_agentcore.runtime import serve_a2a

from model.load import load_model

logger = logging.getLogger(__name__)

WEATHER_TOOLS = {"get_current_weather", "get_weather_byDateTimeRange", "get_current_datetime"}

BASE_PROMPT = """Eres un especialista en clima de viajes. Usa SIEMPRE las herramientas
para obtener datos reales; nunca inventes temperaturas.

Procedimiento obligatorio:
1. NO conoces la fecha de hoy. Antes de responder sobre fechas, llama a
   get_current_datetime con timezone_name="America/Bogota".
2. Si el usuario da fechas y están dentro de los próximos 16 días contados desde
   hoy, llama a get_weather_byDateTimeRange (fechas YYYY-MM-DD) para ese rango.
3. Si pide el clima de ahora, usa get_current_weather.
4. Solo si las fechas están a MÁS de 16 días de hoy, dilo claramente y ofrece
   get_current_weather como referencia.

Responde en español con: temperatura, condiciones, probabilidad de lluvia (si está
disponible) y una recomendación breve para el viajero."""

FALLBACK_PROMPT = """Eres un especialista en clima de viajes, pero el servicio de clima
no está disponible en este momento. Dilo con honestidad al usuario y NO inventes
datos meteorológicos."""


def load_weather_tools():
    try:
        client = MCPClient(
            lambda: stdio_client(
                StdioServerParameters(command=sys.executable, args=["-m", "open_meteo_mcp"])
            ),
            startup_timeout=30,
        )
        client.start()
        tools = [t for t in client.list_tools_sync() if t.tool_name in WEATHER_TOOLS]
        return client, tools
    except Exception as exc:
        logger.warning("MCP de clima no disponible: %s", exc)
        return None, []


_mcp_client, mcp_tools = load_weather_tools()

agent = Agent(
    name="Weather Agent",
    description="Especialista en clima: temperatura, condiciones y pronóstico por ciudad y fechas.",
    model=load_model(),
    system_prompt=BASE_PROMPT if mcp_tools else FALLBACK_PROMPT,
    tools=mcp_tools,
    callback_handler=None,
)

if __name__ == "__main__":
    serve_a2a(StrandsA2AExecutor(agent))