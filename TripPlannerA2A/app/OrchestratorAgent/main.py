import os
import re
import trip_tools
import json
import uuid
import base64
from datetime import date, timedelta

import boto3
from strands import Agent, tool
from strands.agent.a2a_agent import A2AAgent
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model
from trip_tools import build_trip_tools

app = BedrockAgentCoreApp()
AGENTS = {}
WRITE_INTENT = r"\b(crea|crear|crealo|créalo|guarda|guardar|guardalo|guárdalo|registra|registrar|reserva|reservar|genera|generar|actualiza|actualizar|edita|editar|modifica|modificar|cambia|confirmo|confirmar|dale|sí|ok|listo|ese|primero|segundo|tercero|más barato|mas barato)\b"

REGION = os.environ.get("AWS_REGION", "us-east-2")
FLIGHTS_ARN = os.environ.get("FLIGHTS_AGENT_ARN")
WEATHER_ARN = os.environ.get("WEATHER_AGENT_ARN")
FLIGHTS_URL = os.environ.get("FLIGHTS_AGENT_URL", "http://localhost:9000/")
WEATHER_URL = os.environ.get("WEATHER_AGENT_URL", "http://localhost:9001/")

# TODO: poner en "0" cuando el runtime tenga auth JWT (Cognito). Con "1", cualquiera
# que invoque el agente puede elegir el user_id en el payload (solo para desarrollo).
ALLOW_PAYLOAD_USER = os.environ.get("ALLOW_PAYLOAD_USER", "1") == "1"


def _call_runtime(arn: str, text: str) -> str:
    """Llama a un agente A2A desplegado en AgentCore (peticion firmada con IAM)."""
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=str(uuid.uuid4()) + "-orchestrator-session",
        payload=json.dumps(payload).encode(),
        contentType="application/json",
        accept="application/json",
    )
    data = json.loads(resp["response"].read())
    if "error" in data:
        return f"El agente devolvio un error: {data['error']}"
    parts = []
    for art in data.get("result", {}).get("artifacts", []):
        for p in art.get("parts", []):
            if p.get("kind") == "text":
                parts.append(p["text"])
    return "\n".join(parts) or "El agente no devolvio texto."


def _ask(arn, url, text: str) -> str:
    try:
        if arn:
            return _call_runtime(arn, text)
        return str(A2AAgent(endpoint=url)(text).message)
    except Exception as exc:
        return f"No fue posible consultar el agente especialista: {exc}"


@tool
def ask_flights(request: str) -> str:
    """Delega en el Flights Agent la busqueda de vuelos."""
    return _ask(FLIGHTS_ARN, FLIGHTS_URL, request)


@tool
def ask_weather(request: str) -> str:
    """Delega en el Weather Agent la consulta de clima."""
    return _ask(WEATHER_ARN, WEATHER_URL, request)


def _user_id(payload, context) -> str:
    """Identidad del usuario: claim 'sub' del JWT (el runtime ya valido la firma).
    Requiere que el header Authorization este en la allowlist del runtime."""
    headers = getattr(context, "request_headers", None) or {}
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        try:
            part = auth.split(".")[1]
            part += "=" * (-len(part) % 4)
            sub = json.loads(base64.urlsafe_b64decode(part)).get("sub")
            if sub:
                return str(sub)
        except Exception:
            pass
    if ALLOW_PAYLOAD_USER and isinstance(payload, dict) and payload.get("user_id"):
        return str(payload["user_id"])
    raise ValueError("No se pudo identificar al usuario")


def _system_prompt() -> str:
    return (
        f"Eres TripPlanner, un asistente de viajes. Hoy es {date.today().isoformat()}. "
        "Responde siempre en espanol. "
        "Usa ask_flights para vuelos y ask_weather para clima. "
        "Para guardar o consultar viajes, itinerarios y reservas usa las tools de negocio; "
        "nunca inventes ids, usa los que devuelvan las tools. "
        "Las reservas son simuladas: crealas con status SIMULADA salvo que el usuario indique otro estado. "
        "Nunca pidas ni guardes datos de tarjetas. "
        "Si un especialista o una tool falla, dilo con honestidad. "
        "NO crees ni guardes viajes, itinerarios ni reservas hasta que el usuario lo pida de forma explicita; al consultar vuelos y clima solo muestra resultados y propone actividades en el texto. "
        "Solo afirma que creaste o guardaste algo si la tool devolvio exito en esta conversacion; si no, no lo digas. "
        "Si el usuario pide un itinerario, usa get_trips para obtener el tripId y create_itinerary con actividades por dia (hora, titulo y descripcion). "
        f"FECHAS: si el usuario no da fechas exactas, asume salida el {(date.today() + timedelta(days=14)).isoformat()} y regreso segun la "
        "duracion indicada (por ejemplo, 4 dias significa regresar 3 dias despues de la salida). "
        "Di claramente en el texto que fechas asumiste y ofrece cambiarlas. "
        "Al llamar ask_flights y ask_weather incluye las fechas exactas en formato YYYY-MM-DD (ida, vuelta y numero de viajeros). Muestra SOLO vuelos cuya ida y vuelta coincidan exactamente con esas fechas, y el clima de cada dia del viaje, una tarjeta por dia (pidelo dia por dia si hace falta). Empieza el texto diciendo las fechas que asumiste. "
        "Usa SOLO datos que devuelvan los especialistas y las tools; si un dato no esta disponible "
        "usa null en el JSON y escribe 'no disponible' en el texto, nunca la palabra null ni valores inventados. "
        "Cuando haya datos para mostrar, el texto debe ser un resumen breve de 1 a 3 frases, "
        "sin repetir la lista completa, porque los datos se muestran como tarjetas. "
        "Pon los datos al final en bloques ```json, uno por cada tipo, con la forma "
        "{\"type\": \"flights|weather|trips|itinerary|reservations\", \"data\": <lista u objeto>}. "
        "Si consultaste vuelos y clima, emite SIEMPRE dos bloques separados, uno flights y otro weather. "
        "flights: cada item con airline, departure, arrival, return_departure, return_arrival, "
        "price_total, currency y travelers. "
        "weather: una entrada por cada dia del viaje, cada una con date (YYYY-MM-DD, nunca null), "
        "temp_min, temp_max, condition y rain_probability. "
        "Ejemplo de texto correcto: 'Como no indicaste fechas, asumi del 5 al 8 de diciembre. Encontre 5 vuelos "
        "y clima soleado de unos 28 grados. Dime cual prefieres y lo guardo como reserva simulada.' "
        "seguido de los bloques json. "
        "NUNCA enumeres vuelos ni dias en el texto y NUNCA omitas el bloque flights si consultaste vuelos. "
        "Si el usuario pidio clima, SIEMPRE emite el bloque weather con una entrada por dia (fecha, condicion, temperaturas); si el especialista no da todos los dias, repite la consulta dia por dia. En flights, airline es obligatorio: copia el nombre de la aerolinea tal como lo devolvio el especialista. "
        "En los bloques trips, itinerary y reservations copia los objetos que devolvio la tool tal cual, sin quitar campos, incluyendo tripId y reservationId. "
        "Si no hay datos que mostrar, no agregues bloques."
    )


@app.entrypoint
async def invoke(payload, context):
    prompt = payload.get("prompt", "") if isinstance(payload, dict) else str(payload)
    if not isinstance(prompt, str):
        raise ValueError("prompt debe ser un string")
    user_id = _user_id(payload, context)
    trip_tools.STATE["allow_write"] = bool(re.search(WRITE_INTENT, prompt.lower()))
    history = payload.get("history", []) if isinstance(payload, dict) else []
    lines = []
    for m in (history if isinstance(history, list) else [])[-6:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("text"), str):
            who = "Usuario" if m["role"] == "user" else "Asistente"
            lines.append(who + ": " + m["text"][:3000])
    full = prompt
    if lines:
        full = "Conversacion previa:\n" + "\n".join(lines) + "\n\nMensaje actual del usuario: " + prompt
    agent = Agent(
        name="Trip Planner Orchestrator",
        model=load_model(),
        system_prompt=_system_prompt(),
        tools=[ask_flights, ask_weather, *build_trip_tools(user_id)],
        callback_handler=None,
    )
    async for event in agent.stream_async(full):
        if "data" in event:
            yield event["data"]

if __name__ == "__main__":
    app.run()



