import csv
import io
import json
import logging
import os

import boto3

s3 = boto3.client("s3", region_name="eu-west-2")
sqs = boto3.client("sqs")

REFINED_BUCKET = os.environ["REFINED_BUCKET"]
QUEUE_URL = os.environ["QUEUE_URL"]
KMS_KEY = os.environ["KMS_KEY_ARN"]
logger = logging.getLogger()
logger.setLevel(logging.INFO)
REQUIRED = [
    "transaction_id",
    "user_id",
    "amount",
    "currency",
    "merchant_id",
    "channel",
    "ts",
    "ip",
    "country",
    "device_id",
    "card_bin",
    "card_last4",
    "attempts_last_10min",
]


def process_csv(key, bucket):
    logger.info(key)
    if "processed/" in key or "failed/" in key:
        logger.info("first return")

        return
    # if not key.startswith("inbox/") or not key.endswith(".csv"):
    #     logger.info("second return")
    #     return

    try:
        # Read csv
        obj = s3.get_object(Bucket=bucket, Key=key)
        text = obj["Body"].read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        row_num = 0
        results = []
        for row in reader:
            row_num += 1
            for r in REQUIRED:
                if row.get(r, "") == "":
                    raise ValueError(f"Missing '{r}' at row {row_num}")
            row["amount"] = float(row["amount"])
            row["attempts_last_10min"] = int(row["attempts_last_10min"])

            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(row))
            results.append({"row": row_num, "tx": row["transaction_id"]})

        # Write a simple receipt
        receipt_key = "processed/" + os.path.basename(key).replace(
            ".csv", ".receipt.json"
        )
        logger.info(receipt_key)
        logger.info("receipt_key")
        s3.put_object(
            Bucket=REFINED_BUCKET,
            Key=receipt_key,
            Body=json.dumps({"file": key, "rows": results}).encode("utf-8"),
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=KMS_KEY,
            ContentType="application/json",
        )

        # Move file to processed/
        new_key = "processed/" + os.path.basename(key)
        s3.copy_object(
            Bucket=REFINED_BUCKET,
            CopySource={"Bucket": bucket, "Key": key},
            Key=new_key,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=KMS_KEY,
        )
        s3.delete_object(Bucket=bucket, Key=key)

    except Exception as e:
        err_key = "failed/" + os.path.basename(key).replace(".csv", ".receipt.json")
        s3.put_object(
            Bucket=REFINED_BUCKET,
            Key=err_key,
            Body=json.dumps({"file": key, "error": str(e)}).encode("utf-8"),
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=KMS_KEY,
            ContentType="application/json",
        )
        fail_key = "failed/" + os.path.basename(key)
        s3.copy_object(
            Bucket=REFINED_BUCKET,
            CopySource={"Bucket": bucket, "Key": key},
            Key=fail_key,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=KMS_KEY,
        )
        s3.delete_object(Bucket=bucket, Key=key)


def handler(event, context):
    for sqs_record in event["Records"]:
        s3_event = json.loads(sqs_record["body"])

        for rec in s3_event["Records"]:
            logger.info(rec.keys())
            bucket = rec["s3"]["bucket"]["name"]
            key = rec["s3"]["object"]["key"]
            logger.info(bucket)
            # process that one CSV
            process_csv(key, bucket)

    return {"statusCode": 200, "body": json.dumps({"ok": True})}
