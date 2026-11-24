import json, sys, uuid, boto3

ARN = "arn:aws:bedrock-agentcore:us-east-2:843499162128:runtime/TripPlannerA2A_OrchestratorAgent-6kuRBf7eyE"
user_id = sys.argv[1]
prompt = sys.argv[2]

client = boto3.Session(profile_name="cuenta2", region_name="us-east-2").client("bedrock-agentcore")
resp = client.invoke_agent_runtime(
    agentRuntimeArn=ARN,
    runtimeSessionId=str(uuid.uuid4()) + "-test-session",
    payload=json.dumps({"prompt": prompt, "user_id": user_id}).encode(),
)
print(resp["response"].read().decode())
