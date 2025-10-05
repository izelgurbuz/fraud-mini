from datetime import datetime, timezone
import time
import boto3, os 
from decimal import Decimal
session = boto3.Session(region_name=os.environ.get("AWS_REGION"))
ddb = session.resource("dynamodb")
cfn = session.client("cloudformation")
stack = "fraudmini"

response = cfn.describe_stacks(StackName=stack)
outputs = response["Stacks"][0]["Outputs"]

out = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "TransactionsTableName")

TXN_TABLE = ddb.Table(out)

item = {
  "transaction_id": f"seed_{int(time.time())}",
  "user_id": "u_42",
  "amount": Decimal("19.99"),
  "currency": "GBP",
  "merchant_id": "m_AMZ",
  "ts": datetime.now(timezone.utc).isoformat()
}
TXN_TABLE.put_item(Item=item)
print("Wrote item:", item)