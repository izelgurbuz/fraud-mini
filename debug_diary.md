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

## Debug Notes – Local Lambda Debugging with AWS SAM

Goal: Debug Lambda logic locally instead of deploying on AWS every time.

1. Start local API
   sam build
   sam local start-api --env-vars env.json

sam build → packages latest code.

--env-vars → provides environment variables (normally passed by CloudFormation).
Example:

{
"ScoreFunction": {
"TRANSACTIONS_TABLE": "fraudmini-transactions-local",
"RULES_TABLE": "fraudmini-rules-local",
"RULE_VERSION": "v1"
}
}

2. Understand what runs locally

SAM starts a local HTTP API Gateway and also runs the Lambda functions themselves in local Docker containers.

So both your API and function code execute entirely on your machine.

Only AWS services like DynamoDB are remote (unless you use DynamoDB Local).

3. Fixing environment variable errors

At first, the Lambda failed because it couldn’t find environment variables from CloudFormation.

Solution: created env.json and passed it explicitly with --env-vars.

4. Fixing table name errors

DynamoDB requires real physical names, not logical IDs.

Updated env.json values to use full names like:

fraudmini-transactions-111111111111-eu-west-2

5. Seeing logs / prints

print() didn’t show up because the container reused an old build (warm container) and stdout was buffered.

Fixed by:

Rebuilding → sam build

Restarting SAM → sam local start-api

Using proper logging:

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.info("Event: %s", event)

SAM always forwards logger.info to console.

6. Notes about refresh behavior

SAM automatically reloads small code edits, but not always reliably.

For guaranteed updates:

sam build && sam local start-api --env-vars env.json

or use

sam sync --watch

✅ Final outcome

API and Lambda worked locally with real AWS services.

Logs visible, logic debugged, correct response returned.
