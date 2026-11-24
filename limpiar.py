import sys
import boto3
from boto3.dynamodb.conditions import Key

s = boto3.Session(profile_name="default", region_name="us-east-2")
outs = {o["OutputKey"]: o["OutputValue"] for o in s.client("cloudformation").describe_stacks(StackName="tripplanner")["Stacks"][0]["Outputs"]}
user = s.client("cognito-idp").admin_get_user(UserPoolId=outs["UserPoolId"], Username="prueba@tripplanner.com")
sub = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
table = s.resource("dynamodb").Table(outs["TableName"])

items, kwargs = [], {"KeyConditionExpression": Key("PK").eq("USER#" + sub)}
while True:
    r = table.query(**kwargs)
    items += r["Items"]
    if "LastEvaluatedKey" not in r:
        break
    kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]

print("Cuenta:", s.client("sts").get_caller_identity()["Account"], "| Tabla:", outs["TableName"])
for i in items:
    print(i["SK"], "|", i.get("destination") or i.get("title") or "itinerario")
print(len(items), "items")

if len(sys.argv) > 1 and sys.argv[1] == "borrar":
    with table.batch_writer() as b:
        for i in items:
            b.delete_item(Key={"PK": i["PK"], "SK": i["SK"]})
    print("Borrados:", len(items))
else:
    print("Solo listado. Para borrar todo: python limpiar.py borrar")
