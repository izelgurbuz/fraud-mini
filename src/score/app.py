import decimal
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)


TXN_TABLE = os.environ["TRANSACTIONS_TABLE"]
RULES_TABLE = os.environ["RULES_TABLE"]
RULE_VERSION = os.environ.get("RULE_VERSION", "v1")

ddb = boto3.resource("dynamodb")
txns = ddb.Table(TXN_TABLE)
rules_table = ddb.Table(RULES_TABLE)

_rules_cache = None


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


def load_rules():
    global _rules_cache
    if _rules_cache is None:
        items = []
        resp = rules_table.scan(Limit=100)
        items.extend(resp.get("Items", []))
        logger.info(f"Scan resp: {resp}")
        logger.info(f"ITEMS: {items}")

        while "LastEvaluatedKey" in resp:
            resp = rules_table.scan(
                ExclusiveStartKey=resp["LastEvaluatedKey"], Limit=100
            )
            items.extend(resp.get("Items", []))

        _rules_cache = {item["rule_id"]: item for item in items}

    return _rules_cache


def query_recent(user_id, limit=50):
    resp = txns.query(
        IndexName="GSI1_UserTs",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        limit=limit,
    )
    return resp.get("Items", [])


def decide(txn, rules):
    (
        score,
        reasons,
        fired,
    ) = 0, [], []

    r1 = rules["R1"]
    thr = r1["threshold"]
    if float(txn.get("amount", 0)) > thr:
        score += int(r1["weight"])
        reasons.append("amount_above_threshold")
        fired.append("R1")

    r3 = rules["R3"]
    if r3:
        seen = any(
            item.get("device_id") == txn["device_id"]
            for item in query_recent(txn["user_id"])
        )
        if not seen:
            score += int(r3["weight"])
            reasons.append(r3["name"])
            fired.append("R3")

    decision = "allow"
    if score >= 70:
        decision = "block"
    elif score >= 40:
        decision = "challenge"
    return score, decision, reasons, fired


def handler(event, context):
    logger.info(f"Event: {event}")

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
    rules = load_rules()
    score, decision, reasons, fired = decide(txn, rules)

    resp = {
        "transaction_id": txn["transaction_id"],
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "rule_version": RULE_VERSION,
        "rules_fired": fired,
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(resp),
    }
