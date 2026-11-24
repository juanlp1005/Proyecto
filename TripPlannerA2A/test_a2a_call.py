import boto3, json, uuid

REGION = "us-east-2"
ARN = "arn:aws:bedrock-agentcore:us-east-2:843499162128:runtime/TripPlannerA2A_WeatherAgent-4H7XWD8bHa"

client = boto3.client("bedrock-agentcore", region_name=REGION)

payload = {
    "jsonrpc": "2.0",
    "id": str(uuid.uuid4()),
    "method": "message/send",
    "params": {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": "Clima de Madrid el 20 de noviembre de 2026"}],
            "messageId": str(uuid.uuid4()),
        }
    },
}

resp = client.invoke_agent_runtime(
    agentRuntimeArn=ARN,
    runtimeSessionId=str(uuid.uuid4()) + "-a2a-test-session",
    payload=json.dumps(payload).encode(),
    contentType="application/json",
    accept="application/json",
)
body = resp["response"].read().decode("utf-8", "replace")
print(body.encode("ascii", "replace").decode()[:3000])
