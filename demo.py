import boto3

s3 = boto3.client("s3")
cfn = boto3.client("cloudformation")

stacks = cfn.describe_stacks(StackName="fraudmini")

outputs = stacks["Stacks"][0]["Outputs"]
raw_bucket_name = next(
    out["OutputValue"] for out in outputs if out["OutputKey"] == "RawEventsBucketName"
)

KMS_KEY = next(
    out["OutputValue"] for out in outputs if out["OutputKey"] == "AppDataKmsKeyArn"
)

print(KMS_KEY)

with open("sample_transactions.csv", "rb") as f:
    key = "inbox/sample_transactions29.csv"

    s3.put_object(
        Bucket=raw_bucket_name,
        Key=key,
        Body=f,
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=KMS_KEY,
    )
