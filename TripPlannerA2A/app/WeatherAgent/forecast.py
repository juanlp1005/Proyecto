import json
from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=-5))  # Colombia


def _extract_json(text):
    dec = json.JSONDecoder()
    idx = 0
    while True:
        i = text.find("{", idx)
        if i == -1:
            return None
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict) and "weather_data" in obj:
                return obj
        except ValueError:
            pass
        idx = i + 1


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def summarize(text, start=None, end=None):
    data = _extract_json(text)
    if not data or not data.get("weather_data"):
        return {"error": "Sin datos de pronostico para ese rango de fechas.", "detail": text[:300]}

    days = {}
    for row in data["weather_data"]:
        t = row.get("time")
        if not t:
            continue
        try:
            dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        day = dt.astimezone(LOCAL_TZ).date().isoformat()
        days.setdefault(day, []).append(row)

    out = []
    for day in sorted(d for d in days if (not start or d >= start) and (not end or d <= end)):
        rows = days[day]

        def vals(key):
            return [v for v in (_num(r.get(key)) for r in rows) if v is not None]

        def keys_like(sub, exclude=None):
            ks = set()
            for r in rows:
                for k in r:
                    if sub in k and (exclude is None or exclude not in k):
                        ks.add(k)
            return sorted(ks)

        entry = {"date": day}
        temps = vals("temperature_c")
        if temps:
            entry["temp_min_c"] = round(min(temps), 1)
            entry["temp_max_c"] = round(max(temps), 1)
        hum = vals("humidity_percent")
        if hum:
            entry["humidity_avg_percent"] = round(sum(hum) / len(hum))
        cloud = vals("cloud_cover_percent")
        if cloud:
            entry["cloud_cover_avg_percent"] = round(sum(cloud) / len(cloud))
        for k in keys_like("precipitation_probability"):
            v = vals(k)
            if v:
                entry["rain_probability_max_percent"] = round(max(v))
        for k in keys_like("precipitation", exclude="probability"):
            v = vals(k)
            if v:
                entry["precipitation_total_mm"] = round(sum(v), 1)
        wind = vals("wind_speed_kmh")
        if wind:
            entry["wind_max_kmh"] = round(max(wind), 1)
        out.append(entry)

    return {"city": data.get("city"), "timezone": "America/Bogota", "days": out}