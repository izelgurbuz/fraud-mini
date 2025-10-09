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
DEC_TABLE = os.environ["DECISIONS_TABLE"]
RAW_BUCKET = os.environ["RAW_BUCKET"]
KMS_KEY_ARN = os.environ["KMS_KEY_ARN"]
ALERTS_TOPIC = os.environ.get("ALERTS_TOPIC")


ddb = boto3.resource("dynamodb")
txns = ddb.Table(TXN_TABLE)
rules_table = ddb.Table(RULES_TABLE)
decs = ddb.Table(DEC_TABLE)
s3 = boto3.client("s3")
sns = boto3.client("sns")


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
        Limit=limit,
    )
    return resp.get("Items", [])


def decide(txn, rules):
    (
        score,
        reasons,
        fired,
    ) = 0, [], []

    amount = float(txn.get("amount", 0))
    device_id = txn.get("device_id")
    user_id = txn.get("user_id")
    merchant_id = txn.get("merchant_id")
    bin6 = txn.get("card_bin")
    attempts = int(txn.get("attempts_last_10min", 0))

    # R1 amount threshold
    r1 = rules["R1"]
    thr = r1["threshold"]
    if float(amount) > thr:
        score += int(r1["weight"])
        reasons.append("amount_above_threshold")
        fired.append("R1")

    # R3 new_device
    r3 = rules["R3"]
    if r3:
        seen = any(item.get("device_id") == device_id for item in query_recent(user_id))
        if not seen:
            score += int(r3["weight"])
            reasons.append(r3["name"])
            fired.append("R3")
    # R4 attempts
    r4 = rules["R4"]
    attempts = txn["attempts_last_10min"]
    if attempts > int(r4.get("threshold", 5)):
        score += int(r4["weight"])
        reasons.append(r4["name"])
        fired.append("R4")

    r5 = rules["R5"]
    if amount > int(r5.get("threshold", 5)) and merchant_id:
        if not any(
            merchant_id == item["merchant_id"] for item in query_recent(user_id)
        ):
            score += int(r5["weight"])
            reasons.append(r5["name"])
            fired.append("R5")

    r6 = rules["R6"]
    risky = set(r6.get("list", []))
    if bin6 and bin6 in risky:
        score += int(r6["weight"])
        reasons.append(r6["name"])
        fired.append("R6")

    decision = "allow"
    if score >= 70:
        decision = "block"
    elif score >= 30:
        decision = "challenge"
    return score, decision, reasons, fired


def _put_raw(txn, dec_item):
    now = datetime.now(timezone.utc).isoformat()
    key = f"raw/{now}/{txn['transaction_id']}.json"
    blob = json.dumps(
        {"transaction": txn, "decision": dec_item}, separators=(",", ":")
    ).encode("utf-8")
    s3.put_object(
        Bucket=RAW_BUCKET,
        Key=key,
        Body=blob,
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=KMS_KEY_ARN,
        ContentType="application/json",
    )
    return key


def _publish_alert(dec_item):
    if not ALERTS_TOPIC:
        return
    if dec_item["decision"] not in ("challenge", "block"):
        return
    # Keep it minimal: no PII, only IDs and reasons
    subject = f"[fraudmini] {dec_item['decision'].upper()} score={dec_item['score']} id={dec_item['transaction_id']}"
    message = json.dumps(
        {
            "transaction_id": dec_item["transaction_id"],
            "decision": dec_item["decision"],
            "score": dec_item["score"],
            "reasons": dec_item.get("reasons", []),
            "rule_version": dec_item.get("rule_version"),
        }
    )
    sns.publish(TopicArn=ALERTS_TOPIC, Subject=subject[:100], Message=message)


def handler(event, context):
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

    # Idempotency: if already decided, return the same
    txn_id = txn["transaction_id"]
    existing = decs.get_item(Key={"transaction_id": txn_id}).get("Item")
    if existing:
        out = {
            "transaction_id": txn_id,
            "score": int(existing.get("score", 0)),
            "decision": existing.get("decision", "allow"),
            "reasons": existing.get("reasons", []),
            "rule_version": existing.get("rule_version", RULE_VERSION),
            "idempotent": True,
        }
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(out),
        }
    # New transaction path
    txn["created_at"] = datetime.now(timezone.utc).isoformat()

    txns.put_item(Item=_dec(txn))
    rules = load_rules()
    score, decision, reasons, fired = decide(txn, rules)

    dec_item = {
        "transaction_id": txn["transaction_id"],
        "score": int(score),
        "decision": decision,
        "reasons": reasons,
        "rule_version": RULE_VERSION,
        "rules_fired": fired,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    decs.put_item(Item=dec_item)

    try:
        s3_key = _put_raw(txn, dec_item)
    except Exception as e:
        print("S3 write failed:", e)
        s3_key = None

    try:
        _publish_alert(dec_item)
    except Exception as e:
        print("SNS publish failed:", e)

    out = {**dec_item, "s3_key": s3_key}
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(out),
    }
