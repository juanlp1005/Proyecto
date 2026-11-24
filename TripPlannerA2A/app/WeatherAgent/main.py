from strands import Agent, tool
from strands.multiagent.a2a.executor import StrandsA2AExecutor
from bedrock_agentcore.runtime import serve_a2a
from model.load import load_model


@tool
def get_forecast(city: str, date: str) -> dict:
    """Obtiene el pronóstico del clima para una ciudad y fecha (datos simulados)."""
    return {
        "city": city,
        "date": date,
        "condition": "Soleado",
        "temp_celsius": 28,
        "humidity": 65,
    }


SYSTEM_PROMPT = (
    "Eres un agente especialista en clima. Usa get_forecast para consultar "
    "el pronóstico y responde de forma clara."
)

agent = Agent(
    name="Weather Agent",
    description="Consulta el pronóstico del clima para una ciudad.",
    model=load_model(),
    system_prompt=SYSTEM_PROMPT,
    tools=[get_forecast],
)

if __name__ == "__main__":
    serve_a2a(StrandsA2AExecutor(agent))