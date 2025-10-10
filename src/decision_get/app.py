import decimal
import json
import os

import boto3

DEC_TABLE = os.environ["DECISIONS_TABLE"]


ddb = boto3.resource("dynamodb")

decs = ddb.Table(DEC_TABLE)


def _float(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dict):
        return {k: _float(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_float(x) for x in v]
    return v


def handler(event, context):
    txid = event.get("pathParameters", {}).get("transaction_id")

    if not txid:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "transaction_id is required"}),
        }
    item = decs.get_item(Key={"transaction_id": txid}).get("Item")
    if not item:
        return {"statusCode": 404, "body": json.dumps({"error": "not found"})}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(_float(item)),
    }
