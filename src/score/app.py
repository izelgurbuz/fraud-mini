import json


def _bad(msg):
    return {"statusCode": 400, "body": json.dumps({"error": msg})}


def handler(event, context):
    if "body" not in event:
        return _bad("Missing body")

    try:
        txn = json.load(event["body"])
    except Exception:
        return _bad("Invalid JSON")

    needed = ["transaction_id", "user_id", "ts"]
    missing = [k for k in needed if k not in txn]

    if missing:
        return _bad(f"Missing fields {','.join(missing)}")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"ok": True, "echo": {"transaction_id": txn["transaction_id"]}}
        ),
    }
