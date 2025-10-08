# Fraudmini Debug Journey (Summary)

1 - Initial error  
I ran curl to test Lambda and got:
{"message": "Invalid request body"}

I tried to debug but saw no logs — CloudWatch wasn’t configured for API Gateway.

---

2 -Enabling API Gateway logging  
I added CloudWatch log settings in the YAML:

- Created a LogGroup
- Linked it under Globals → Api → AccessLogSetting

But deployment failed:
“CloudWatch Logs role ARN must be set in account settings.”

So I created a role manually in the AWS console, attached
`AmazonAPIGatewayPushToCloudWatchLogs`, and added its ARN under  
**API Gateway → Settings → CloudWatch log role ARN**.

✅ Logs started appearing — both default per-path logs and my custom formatted API Gateway logs.

---

3 - Found validation issue  
From the new logs, I saw requests failed **before Lambda**, due to schema validation.  
The schema required `created_at`, but my request body didn’t include it.

→ I removed `created_at` from `required:` (kept it in properties).  
→ API Gateway then passed the request to Lambda.

---

4- - Lambda JSON parsing fix  
Lambda crashed because of:

```python
txn = json.load(event["body"])

Replaced with:

txn = json.loads(event["body"])

KMS permission error
Next error:
KMS key access denied (AWSKMSException)

Cause:
My DynamoDB tables used a custom KMS key,
but the Lambda execution role didn’t have permission to use that key.

Fix:
Added this IAM statement inside the Lambda:

- Statement:
    Effect: Allow
    Action:
      - kms:Encrypt
      - kms:Decrypt
      - kms:ReEncrypt*
      - kms:GenerateDataKey*
      - kms:DescribeKey
    Resource: !GetAtt AppDataKey.Arn


✅ Lambda got access to use KMS for encrypted writes.

6 - Circular dependency error
Then deployment failed with:
“Circular dependency between resources: [AppDataKey, ScoreFunctionRole, …]”

Why:
I had added a key policy in AppDataKey that referenced the Lambda’s IAM role:

Principal:
  AWS: !GetAtt ScoreFunction.Role.Arn


But Lambda also referenced the same KMS key via !GetAtt AppDataKey.Arn.
This created a dependency loop.

Fix:
-> Removed that policy block from the KMS key.
-> Kept only the IAM permissions inside Lambda.

Loop resolved, stack deployed successfully.

7 -Final test
After redeploy:

curl -sS "${API_URL}/score" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @txn.json | jq


Response:

{ "ok": true, "echo": { "transaction_id": "txn_1" } }


API Gateway logging works
Validation correct
Lambda parses input
KMS + DynamoDB working
Fully functional deployment
```
