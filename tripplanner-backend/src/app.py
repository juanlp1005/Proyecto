"""TripPlanner AI - operaciones de negocio (Lambda -> DynamoDB).

Dos formas de invocación:
  1) API Gateway (HTTP API + JWT de Cognito): el userId sale SIEMPRE del claim `sub`.
  2) Invoke directo desde las Tools del agente (IAM): el userId viene en el evento
     (lo pone el código de la Tool desde la sesión, nunca el LLM).
"""
import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

RES_TYPES = {"VUELO", "HOTEL", "ACTIVIDAD"}
RES_STATES = {"SIMULADA", "PENDIENTE", "CONFIRMADA"}
TRIP_FIELDS = {"destination", "origin", "start_date", "end_date", "travelers", "budget", "notes"}
RES_FIELDS = {"type", "title", "provider", "price", "date", "details", "status"}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


# ---------- utilidades ----------
def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default, ensure_ascii=False),
    }


def _parse(event):
    if "requestContext" in event:  # viene de API Gateway
        claims = event["requestContext"].get("authorizer", {}).get("jwt", {}).get("claims", {})
        user = claims.get("sub")
        if not user:
            raise ApiError(401, "No autorizado")
        data = {}
        raw = event.get("body")
        if raw:
            try:
                data.update(json.loads(raw))
            except ValueError:
                raise ApiError(400, "El cuerpo debe ser JSON válido")
        data.update(event.get("queryStringParameters") or {})
        data.update(event.get("pathParameters") or {})
    else:  # invoke directo desde una Tool
        user = event.get("userId")
        if not user:
            raise ApiError(400, "userId requerido")
        data = {k: v for k, v in event.items() if k != "userId"}
    if not isinstance(data, dict):
        raise ApiError(400, "Cuerpo inválido")
    return str(user), data


def endpoint(fn):
    def wrapper(event, context):
        try:
            user, data = _parse(event)
            status, body = fn(user, data)
            return _resp(status, body)
        except ApiError as e:
            return _resp(e.status, {"error": e.message})
        except Exception:
            logger.exception("Error no controlado")
            return _resp(500, {"error": "Error interno del servidor"})
    return wrapper


def _now():
    return datetime.now(timezone.utc).isoformat()


def _pk(user):
    return f"USER#{user}"


def _clean(item):
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def _text(v, name, max_len=300, required=False):
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise ApiError(400, f"{name} es obligatorio")
        return None
    if not isinstance(v, str):
        raise ApiError(400, f"{name} debe ser texto")
    return v.strip()[:max_len]


def _date(v, name):
    try:
        date.fromisoformat(str(v))
    except ValueError:
        raise ApiError(400, f"{name} debe tener formato YYYY-MM-DD")
    return str(v)


def _int(v, name, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} debe ser un número entero")
    if not lo <= n <= hi:
        raise ApiError(400, f"{name} debe estar entre {lo} y {hi}")
    return n


def _num(v, name):
    try:
        n = Decimal(str(v))
    except Exception:
        raise ApiError(400, f"{name} debe ser numérico")
    if n < 0:
        raise ApiError(400, f"{name} no puede ser negativo")
    return n


def _update(user, sk, fields):
    if not fields:
        raise ApiError(400, "No hay campos para actualizar")
    fields["updated_at"] = _now()
    names = {f"#f{i}": k for i, k in enumerate(fields)}
    values = {f":v{i}": v for i, v in enumerate(fields.values())}
    expr = "SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields)))
    try:
        r = table.update_item(
            Key={"PK": _pk(user), "SK": sk},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(404, "Recurso no encontrado")
        raise
    return _clean(r["Attributes"])


def _require_trip(user, trip_id):
    trip_id = _text(trip_id, "tripId", 64, required=True)
    r = table.get_item(Key={"PK": _pk(user), "SK": f"TRIP#{trip_id}"})
    if "Item" not in r:
        raise ApiError(404, "Viaje no encontrado")
    return trip_id, r["Item"]


# ---------- validación ----------
def _trip_fields(data, partial):
    out = {}
    if "destination" in data or not partial:
        out["destination"] = _text(data.get("destination"), "destination", 100, required=True)
    if "origin" in data or not partial:
        out["origin"] = _text(data.get("origin"), "origin", 100, required=True)
    if "start_date" in data or not partial:
        out["start_date"] = _date(data.get("start_date"), "start_date")
    if "end_date" in data or not partial:
        out["end_date"] = _date(data.get("end_date"), "end_date")
    if "travelers" in data or not partial:
        out["travelers"] = _int(data.get("travelers"), "travelers", 1, 20)
    if "budget" in data or not partial:
        out["budget"] = _num(data.get("budget"), "budget")
    if "notes" in data:
        out["notes"] = _text(data.get("notes"), "notes", 1000)
    return {k: v for k, v in out.items() if v is not None}


def _days(data):
    days = data.get("days")
    if not isinstance(days, list) or not 1 <= len(days) <= 31:
        raise ApiError(400, "days debe ser una lista de 1 a 31 días")
    out = []
    for d in days:
        if not isinstance(d, dict):
            raise ApiError(400, "Cada día debe ser un objeto")
        acts = d.get("activities", [])
        if not isinstance(acts, list) or len(acts) > 20:
            raise ApiError(400, "activities debe ser una lista de máximo 20")
        out.append({
            "date": _date(d.get("date"), "date"),
            "activities": [
                {
                    "time": _text(a.get("time"), "time", 20) or "",
                    "title": _text(a.get("title"), "title", 120, required=True),
                    "description": _text(a.get("description"), "description", 500) or "",
                }
                for a in acts if isinstance(a, dict)
            ],
        })
    return out


def _res_fields(data, partial):
    out = {}
    if "type" in data or not partial:
        t = str(data.get("type", "")).upper()
        if t not in RES_TYPES:
            raise ApiError(400, f"type debe ser uno de {sorted(RES_TYPES)}")
        out["type"] = t
    if "title" in data or not partial:
        out["title"] = _text(data.get("title"), "title", 150, required=True)
    if "provider" in data:
        out["provider"] = _text(data.get("provider"), "provider", 100)
    if "price" in data:
        out["price"] = _num(data.get("price"), "price")
    if "date" in data:
        out["date"] = _date(data.get("date"), "date")
    if "details" in data:
        out["details"] = _text(data.get("details"), "details", 1000)
    if "status" in data:
        s = str(data.get("status")).upper()
        if s not in RES_STATES:
            raise ApiError(400, f"status debe ser uno de {sorted(RES_STATES)}")
        out["status"] = s
    return {k: v for k, v in out.items() if v is not None}


# ---------- viajes ----------
@endpoint
def create_trip(user, data):
    f = _trip_fields(data, partial=False)
    if f["end_date"] < f["start_date"]:
        raise ApiError(400, "end_date no puede ser anterior a start_date")
    trip_id = uuid.uuid4().hex[:12]
    item = {"PK": _pk(user), "SK": f"TRIP#{trip_id}", "tripId": trip_id,
            "created_at": _now(), "updated_at": _now(), **f}
    table.put_item(Item=item)
    return 201, _clean(item)


@endpoint
def get_trips(user, data):
    if data.get("tripId"):
        _, item = _require_trip(user, data["tripId"])
        return 200, {"trip": _clean(item)}
    r = table.query(KeyConditionExpression=Key("PK").eq(_pk(user)) & Key("SK").begins_with("TRIP#"))
    return 200, {"trips": [_clean(i) for i in r["Items"]]}


@endpoint
def update_trip(user, data):
    trip_id, trip = _require_trip(user, data.get("tripId"))
    f = _trip_fields(data, partial=True)
    start = f.get("start_date", trip["start_date"])
    end = f.get("end_date", trip["end_date"])
    if end < start:
        raise ApiError(400, "end_date no puede ser anterior a start_date")
    return 200, _update(user, f"TRIP#{trip_id}", f)


# ---------- itinerarios ----------
@endpoint
def create_itinerary(user, data):
    trip_id, _ = _require_trip(user, data.get("tripId"))
    item = {"PK": _pk(user), "SK": f"ITIN#{trip_id}", "tripId": trip_id,
            "days": _days(data), "created_at": _now(), "updated_at": _now()}
    table.put_item(Item=item)
    return 201, _clean(item)


@endpoint
def update_itinerary(user, data):
    trip_id, _ = _require_trip(user, data.get("tripId"))
    return 200, _update(user, f"ITIN#{trip_id}", {"days": _days(data)})


@endpoint
def get_itinerary(user, data):
    trip_id, _ = _require_trip(user, data.get("tripId"))
    r = table.get_item(Key={"PK": _pk(user), "SK": f"ITIN#{trip_id}"})
    if "Item" not in r:
        raise ApiError(404, "El viaje aún no tiene itinerario")
    return 200, _clean(r["Item"])


# ---------- reservas ----------
@endpoint
def create_reservation(user, data):
    trip_id, _ = _require_trip(user, data.get("tripId"))
    f = _res_fields(data, partial=False)
    f.setdefault("status", "SIMULADA")  # por defecto simulada
    res_id = uuid.uuid4().hex[:12]
    item = {"PK": _pk(user), "SK": f"RES#{trip_id}#{res_id}", "tripId": trip_id,
            "reservationId": res_id, "created_at": _now(), "updated_at": _now(), **f}
    table.put_item(Item=item)
    return 201, _clean(item)


@endpoint
def get_reservations(user, data):
    prefix = f"RES#{data['tripId']}#" if data.get("tripId") else "RES#"
    r = table.query(KeyConditionExpression=Key("PK").eq(_pk(user)) & Key("SK").begins_with(prefix))
    return 200, {"reservations": [_clean(i) for i in r["Items"]]}


@endpoint
def update_reservation(user, data):
    trip_id, _ = _require_trip(user, data.get("tripId"))
    res_id = _text(data.get("reservationId"), "reservationId", 64, required=True)
    return 200, _update(user, f"RES#{trip_id}#{res_id}", _res_fields(data, partial=True))

@endpoint
def delete_reservation(user, data):
    trip_id, _ = _require_trip(user, data.get("tripId"))
    res_id = _text(data.get("reservationId"), "reservationId", 64, required=True)
    try:
        table.delete_item(
            Key={"PK": _pk(user), "SK": f"RES#{trip_id}#{res_id}"},
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(404, "Reserva no encontrada")
        raise
    return 200, {"deleted": res_id}
