import decimal
import json
import os
from datetime import datetime, timezone

import boto3

TXN_TABLE = os.environ["TRANSACTIONS_TABLE"]
ddb = boto3.resource("dynamodb")
txns = ddb.Table(TXN_TABLE)


def _bad(msg):
    return {"statusCode": 400, "body": json.dumps({"error": msg})}


def _dec(v):
    if isinstance(v, float):
        return decimal.Decimal(str(v))
    if isinstance(v, dict):
        return {k: _dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_dec(x) for x in v]
    return v


def handler(event, context):
    print("EVENT:", json.dumps(event)[:500])
    if "body" not in event:
        return _bad("Missing body")

    try:
        txn = json.loads(event["body"])
    except Exception:
        return _bad("Invalid JSON")

    needed = ["transaction_id", "user_id", "ts"]
    missing = [k for k in needed if k not in txn]

    if missing:
        return _bad(f"Missing fields {','.join(missing)}")

    txn["created_at"] = datetime.now(timezone.utc).isoformat()

    txns.put_item(Item=_dec(txn))

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"ok": True, "echo": {"transaction_id": txn["transaction_id"]}}
        ),
    }
