"""Tools de negocio de TripPlanner: cada una invoca su Lambda (Lambda -> DynamoDB).

El user_id NO es parametro de ninguna Tool: lo inyecta el codigo (closure) desde
la identidad del usuario, asi el LLM no puede elegir de quien son los datos.
"""
import json
import os
from typing import Optional

import boto3
from strands import tool

REGION = os.environ.get("AWS_REGION", "us-east-2")
STACK = os.environ.get("TRIPPLANNER_STACK", "tripplanner")

_lambda = boto3.client("lambda", region_name=REGION)
_cfn = boto3.client("cloudformation", region_name=REGION)
_names = {}


def _fn(logical_id: str) -> str:
    """Resuelve el nombre fisico de la Lambda a partir del stack de SAM."""
    if not _names:
        resources = _cfn.describe_stack_resources(StackName=STACK)["StackResources"]
        for r in resources:
            if r["ResourceType"] == "AWS::Lambda::Function":
                _names[r["LogicalResourceId"]] = r["PhysicalResourceId"]
    return _names[logical_id]


WRITE_OPS = {"UpdatePreferencesFn", "CreateTripFn", "UpdateTripFn", "CreateItineraryFn", "UpdateItineraryFn", "CreateReservationFn", "UpdateReservationFn"}
STATE = {"allow_write": True}




def _invoke(logical_id: str, user_id: str, args: dict) -> str:
    if logical_id in WRITE_OPS and not STATE["allow_write"]:
        return "Accion bloqueada: el usuario aun no pidio guardar ni modificar nada. Muestra opciones y preguntale si quiere guardarlas."
    payload = {**{k: v for k, v in args.items() if v is not None}, "userId": user_id}
    try:
        r = _lambda.invoke(FunctionName=_fn(logical_id), Payload=json.dumps(payload).encode())
        out = json.loads(r["Payload"].read())
    except Exception as exc:
        return f"No fue posible ejecutar la operacion: {exc}"
    status = out.get("statusCode", 500)
    body = out.get("body", "")
    if status >= 400:
        return f"Error {status}: {body}"
    return body


def build_trip_tools(user_id: str) -> list:
    """Crea las Tools ligadas al usuario autenticado de esta peticion."""

    @tool
    def create_trip(destination: str, origin: str, start_date: str, end_date: str,
                    travelers: int, budget: float, notes: Optional[str] = None) -> str:
        """Crea un viaje del usuario. Fechas en formato YYYY-MM-DD. Devuelve el viaje con su tripId."""
        return _invoke("CreateTripFn", user_id, dict(
            destination=destination, origin=origin, start_date=start_date,
            end_date=end_date, travelers=travelers, budget=budget, notes=notes))

    @tool
    def get_trips(trip_id: Optional[str] = None) -> str:
        """Consulta los viajes del usuario. Si se da trip_id devuelve solo ese viaje."""
        return _invoke("GetTripsFn", user_id, dict(tripId=trip_id))

    @tool
    def update_trip(trip_id: str, destination: Optional[str] = None, origin: Optional[str] = None,
                    start_date: Optional[str] = None, end_date: Optional[str] = None,
                    travelers: Optional[int] = None, budget: Optional[float] = None,
                    notes: Optional[str] = None) -> str:
        """Actualiza datos de un viaje existente. Solo envia los campos que cambian."""
        return _invoke("UpdateTripFn", user_id, dict(
            tripId=trip_id, destination=destination, origin=origin, start_date=start_date,
            end_date=end_date, travelers=travelers, budget=budget, notes=notes))

    @tool
    def create_itinerary(trip_id: str, days: list[dict]) -> str:
        """Crea el itinerario de un viaje. days es una lista de
        {"date": "YYYY-MM-DD", "activities": [{"time": "09:00", "title": "...", "description": "..."}]}."""
        return _invoke("CreateItineraryFn", user_id, dict(tripId=trip_id, days=days))

    @tool
    def update_itinerary(trip_id: str, days: list[dict]) -> str:
        """Reemplaza el itinerario de un viaje con la lista completa de dias (mismo formato que create_itinerary)."""
        return _invoke("UpdateItineraryFn", user_id, dict(tripId=trip_id, days=days))

    @tool
    def get_itinerary(trip_id: str) -> str:
        """Consulta el itinerario guardado de un viaje."""
        return _invoke("GetItineraryFn", user_id, dict(tripId=trip_id))

    @tool
    def create_reservation(trip_id: str, type: str, title: str, provider: Optional[str] = None,
                           price: Optional[float] = None, date: Optional[str] = None,
                           details: Optional[str] = None, status: Optional[str] = None) -> str:
        """Registra una reserva asociada a un viaje. type: VUELO, HOTEL o ACTIVIDAD.
        status: SIMULADA (por defecto), PENDIENTE o CONFIRMADA. Nunca pedir datos de tarjeta."""
        return _invoke("CreateReservationFn", user_id, dict(
            tripId=trip_id, type=type, title=title, provider=provider,
            price=price, date=date, details=details, status=status))

    @tool
    def get_reservations(trip_id: Optional[str] = None) -> str:
        """Consulta las reservas del usuario; con trip_id solo las de ese viaje."""
        return _invoke("GetReservationsFn", user_id, dict(tripId=trip_id))

    @tool
    def update_reservation(trip_id: str, reservation_id: str, title: Optional[str] = None,
                           provider: Optional[str] = None, price: Optional[float] = None,
                           date: Optional[str] = None, details: Optional[str] = None,
                           status: Optional[str] = None) -> str:
        """Actualiza una reserva o su estado (SIMULADA, PENDIENTE, CONFIRMADA)."""
        return _invoke("UpdateReservationFn", user_id, dict(
            tripId=trip_id, reservationId=reservation_id, title=title, provider=provider,
            price=price, date=date, details=details, status=status))

    @tool
    def get_preferences() -> str:
        """Consulta las preferencias de viaje guardadas del usuario (actividades, nivel de presupuesto, restricciones)."""
        return _invoke("GetPreferencesFn", user_id, {})

    @tool
    def update_preferences(preferred_activities: Optional[str] = None, budget_level: Optional[str] = None,
                           restrictions: Optional[str] = None, notes: Optional[str] = None) -> str:
        """Guarda o actualiza las preferencias de viaje del usuario. budget_level: ECONOMICO, MEDIO o ALTO.
        Solo envia los campos que cambian."""
        return _invoke("UpdatePreferencesFn", user_id, dict(
            preferred_activities=preferred_activities, budget_level=budget_level,
            restrictions=restrictions, notes=notes))

    return [get_preferences, update_preferences, create_trip, get_trips, update_trip, create_itinerary, update_itinerary,
            get_itinerary, create_reservation, get_reservations, update_reservation]

