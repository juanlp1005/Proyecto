import json, uuid, boto3

ARN = "arn:aws:bedrock-agentcore:us-east-2:293694139479:runtime/TripPlannerA2A_WeatherAgent-Dhnxbf3fgF"
client = boto3.client("bedrock-agentcore", region_name="us-east-2")

def ask(text):
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {"message": {
            "role": "user",
            "messageId": str(uuid.uuid4()),
            "parts": [{"kind": "text", "text": text}],
        }},
    }
    r = client.invoke_agent_runtime(
        agentRuntimeArn=ARN,
        runtimeSessionId=str(uuid.uuid4()),
        contentType="application/json",
        accept="application/json",
        payload=json.dumps(payload).encode("utf-8"),
    )
    data = json.loads(r["response"].read())
    out = []
    for a in data.get("result", {}).get("artifacts", []):
        for p in a.get("parts", []):
            out.append(p.get("text", ""))
    return "\n".join(out) or json.dumps(data)[:800]

for q in ["Clima en Cartagena del 26 al 29 de noviembre de 2026",
          "Clima en Bogota del 26 al 29 de noviembre de 2026"]:
    print("\n### " + q)
    print(ask(q).encode("ascii", "replace").decode())