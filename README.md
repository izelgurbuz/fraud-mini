# 🧠 fraudmini — Serverless Fraud Detection Pipeline (AWS)

**fraudmini** is a fully serverless, event-driven data pipeline for ingesting, processing, and scoring financial transaction CSVs on **AWS**.  
It demonstrates secure, automated cloud architecture using modern **Infrastructure-as-Code**, event orchestration, and CI/CD best practices.

---

## 🚀 Overview

1. **Upload:** CSV files are dropped into the **RawEvents** S3 bucket (`inbox/` prefix).
2. **Trigger:** The bucket notifies an **SQS queue** (`RawEventsQueue`), decoupling storage from compute.
3. **Ingest:** The **BatchIngest Lambda** reads the file, validates transactions, and publishes each row as a message to another queue (`TransactionsQueue`).
4. **Score:** The **ScoreFunction Lambda** consumes those messages, applies rule-based scoring, writes results to **DynamoDB**, and publishes alerts to an **SNS** topic if risk exceeds threshold.
5. **Audit:** Processed files and receipts are moved to the **RefinedEvents** bucket (`processed/`, `failed/` prefixes).

This design provides **asynchronous, scalable, and fault-tolerant** processing — no polling, no servers.

---

## 🧩 Tech Stack

| Layer             | Service                   | Purpose                                        |
| ----------------- | ------------------------- | ---------------------------------------------- |
| **Compute**       | AWS Lambda                | Batch ingestion & transaction scoring          |
| **Storage**       | Amazon S3                 | Raw → refined event buckets for data lifecycle |
| **Messaging**     | Amazon SQS                | Decouples event flow (Raw → Transactions)      |
| **Database**      | DynamoDB                  | Stores transactions, rules, and decisions      |
| **Notifications** | Amazon SNS                | Sends high-risk alerts                         |
| **Security**      | AWS KMS                   | Encrypts data at rest and in transit           |
| **Identity**      | IAM + OIDC                | Fine-grained permissions & CI/CD trust         |
| **Monitoring**    | CloudWatch                | Logs & alarms for Lambda errors                |
| **IaC**           | AWS SAM (CloudFormation)  | Declarative, repeatable deployments            |
| **CI/CD**         | GitHub Actions + AWS OIDC | Automated build/deploy from `main` branch      |

---

## 🔐 Security Highlights

- All S3 buckets enforce **KMS encryption** and deny unencrypted PUTs.
- **IAM least privilege**: each function can only access its own queues/buckets.
- **HTTPS enforced** via `aws:SecureTransport` conditions.
- **GitHub OIDC** trust for CI/CD — _no static AWS keys_.
- End-to-end encryption between all AWS components.

---

## ⚙️ Deployment

### Prerequisites

- AWS CLI & SAM CLI installed
- Python 3.11
- AWS account with appropriate permissions

### Deploy

```bash
sam build
sam deploy --guided
```

After deployment, note these outputs:

- RawEventsBucketName

- ApiUrl

## Running the Pipeline

Place a CSV file into the inbox/ folder of your raw events bucket:

```bash
python scripts/upload_csv.py
```

The pipeline automatically triggers:

`S3 → RawEventsQueue → BatchIngest → TransactionsQueue → ScoreFunction`

Results:

✅ Receipts & processed files → refined-events/processed/

❌ Failed files → refined-events/failed/

🔔 Alerts → SNS topic & CloudWatch Logs

🧭 Architecture Diagram
S3 (raw) ─▶ SQS (RawEvents) ─▶ Lambda (BatchIngest)
│
▼
SQS (Transactions) ─▶ Lambda (Score)
│
├─▶ DynamoDB (Transactions, Decisions, Rules)
└─▶ SNS (Alerts)

💡 Features Demonstrated

- Event-driven design (no cron jobs or polling)

- Asynchronous, scalable ingestion

- Serverless compute pipeline

- Infrastructure-as-Code with CI/CD

- Secure data encryption & IAM separation

Built as a realistic one-developer finance-tech project to demonstrate:

Hands-on AWS proficiency (Lambda, SQS, S3, KMS, IAM, SAM)

Secure data handling in production-like pipelines

Practical event-driven architecture for transaction analytics

```bash
                    ┌─────────────────────────────┐
                    │     fraudmini system        │
                    └─────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────┐
│                1. RawEventsBucket (S3)                 │
│  - KMS-encrypted with AppDataKey                       │
│  - Event: ObjectCreated:* on inbox/*.csv               │
│  - Sends notification to RawEventsQueue (SQS)          │
│                                                        │
│  BucketPolicy:                                         │
│    - Deny insecure transport                           │
│    - Enforce KMS encryption on PUT                     │
│                                                        │
│  KMS Policy:                                           │
│    - Allows S3 to GenerateDataKey + Decrypt            │
│                                                        │
└────────────────────────────────────────────────────────┘
                                   │
                                   │  (S3 → SQS Notification)
                                   ▼
┌────────────────────────────────────────────────────────┐
│                2. RawEventsQueue (SQS)                 │
│  - KMS-encrypted (AppDataKey)                          │
│  - QueuePolicy allows S3:s3.amazonaws.com to SendMessage│
│    only from RawEventsBucket ARN + same AWS account     │
│                                                        │
│  Event Source for: BatchIngest Lambda                  │
└────────────────────────────────────────────────────────┘
                                   │
                                   │  (SQS → Lambda trigger)
                                   ▼
┌────────────────────────────────────────────────────────┐
│                3. BatchIngestFunction (Lambda)         │
│  - Reads events from RawEventsQueue                    │
│  - Downloads CSV from RawEventsBucket                  │
│  - Validates & parses records                          │
│  - Sends each record → TransactionsQueue (SQS)         │
│  - Writes receipts + copies to RefinedEventsBucket     │
│  - Deletes processed CSV from RawEventsBucket          │
│                                                        │
│  IAM Policy:                                           │
│    - s3:GetObject/DeleteObject on RawEventsBucket      │
│    - s3:PutObject on RefinedEventsBucket               │
│    - sqs:SendMessage on TransactionsQueue              │
│    - kms:Encrypt/Decrypt on AppDataKey                 │
└────────────────────────────────────────────────────────┘
                                   │
                                   │  (SQS → Lambda trigger)
                                   ▼
┌────────────────────────────────────────────────────────┐
│                4. TransactionsQueue (SQS)              │
│  - Buffers parsed transactions                         │
│  - Event Source for ScoreFunction                      │
└────────────────────────────────────────────────────────┘
                                   │
                                   │  (SQS → Lambda trigger)
                                   ▼
┌────────────────────────────────────────────────────────┐
│                5. ScoreFunction (Lambda)               │
│  - Processes transaction messages                      │
│  - Evaluates fraud/risk logic                          │
│  - Writes results to DynamoDB Tables                   │
│  - Publishes alerts to AlertsTopic (SNS)               │
│  - Uses AppDataKey for encryption/decryption            │
└────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────┐
│                6. RefinedEventsBucket (S3)             │
│  - Receipts (.json) and processed copies (.csv)        │
│  - KMS-encrypted with AppDataKey                       │
│  - Not part of trigger chain → prevents recursion      │
└────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────┐
│                7. AlertsTopic (SNS)                    │
│  - Receives high-risk alerts from ScoreFunction        │
│  - Can later fan-out to email/SMS notifications        │
└────────────────────────────────────────────────────────┘
```
