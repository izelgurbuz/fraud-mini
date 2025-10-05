import boto3, os 
import json
session = boto3.Session(region_name=os.environ.get("AWS_REGION"))
ddb = session.resource("dynamodb")
cfn = session.client("cloudformation")
stack = "fraudmini"

response = cfn.describe_stacks(StackName=stack)
outputs = response["Stacks"][0]["Outputs"]

out = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "RulesTableName")
table = ddb.Table(out)

# os.path.dirname(__file__)  = the folder containing the script
# .. -> go one level up (to project root)
# data/rules_seed.json -> the seed file
with open(os.path.join(os.path.dirname(__file__), "..", "data", "rules_seed.json")) as f:
    rules = json.load(f)

# Each call to bw.put_item() adds the item to an in-memory buffer.
# When that buffer reaches 25 items (the DynamoDB BatchWriteItem limit),
# boto3 automatically sends them all together in one network request using BatchWriteItem.
# If DynamoDB returns any “throttled” or “unprocessed” items boto3 automatically retries them with exponential backoff.
# When you exit the with block, boto3 flushes any remaining items that didn’t fill a full batch.
with table.batch_writer() as bw:
    for r in rules:
        bw.put_item(Item=r)

print(f"Seeded {len(rules)} rules into {out}")