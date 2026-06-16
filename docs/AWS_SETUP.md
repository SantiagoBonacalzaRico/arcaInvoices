# AWS account setup — prerequisites for deploying arcaInvoices

These are the **manual, one-time steps you must do in your AWS account** before
the Terraform (which provisions EC2 / RDS / ECR / etc.) can run. Do them in
order. Most are free; the only ongoing cost in this list is nothing — billing
alarms and IAM are free.

> ⚠️ **Free-tier eligibility:** the 12-month Free Tier only applies to an AWS
> account **less than 12 months old**. If your account is older, EC2 + RDS will
> cost roughly **$15–20/month**. If you want to start the clock fresh, create a
> brand-new account.

### How to check if your account is still Free-Tier eligible

After the CLI is configured (step 6), run:

```bash
# 1) When the account was created (12 months from here = free-tier window)
aws iam get-account-summary >/dev/null 2>&1 && \
  aws organizations describe-account --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --query 'Account.JoinedTimestamp' --output text 2>/dev/null || \
  echo "Check the console: Billing & Cost Management → Free Tier (left nav)."
```

Most reliable: open **Billing and Cost Management → Free Tier** in the console.
If that page shows free-tier *usage tracking* (e.g. "EC2 750 hrs"), you're
eligible; if it says free tier has ended, you're not. I'll also help you read it.

---

## 0. Pick a region

Use **`sa-east-1` (São Paulo)** — closest to Argentina (lowest latency) and it
supports everything we need (EC2 `t3.micro`, RDS `db.t4g.micro`). Write it down;
every step uses the same region. (Route 53 and IAM are global and unaffected.)

---

## 1. Create / sign in to the AWS account

If you don't have one: https://aws.amazon.com/ → **Create an AWS Account**.
Needs an email, a **credit card** (for verification; Free Tier won't charge if
you stay within limits), and phone verification. Choose the **Basic (free)**
support plan.

---

## 2. Secure the root user (do NOT use root for daily work)

1. Sign in as the **root user** (the email you registered with).
2. Top-right account menu → **Security credentials**.
3. **Enable MFA** on the root user (authenticator app like Google Authenticator
   or Authy). This is the single most important security step.
4. Do **not** create access keys for root. Close the page.

---

## 3. Create an admin IAM user (for you + Terraform)

1. Go to the **IAM** console → **Users** → **Create user**.
2. User name: `arca-admin`. ✅ "Provide user access to the AWS Management
   Console" is optional; you can leave it off (we mainly need CLI access).
3. Permissions → **Attach policies directly** → check **`AdministratorAccess`**.
   *(Broad on purpose to keep setup simple; we can tighten later.)*
4. Create the user.
5. Open the user → **Security credentials** tab → **Create access key** →
   choose **Command Line Interface (CLI)** → create.
6. **Copy the Access key ID and Secret access key now** (the secret is shown
   once). Keep them somewhere safe — a password manager.

> 🔐 **Never paste the secret access key into this chat or commit it.** You'll
> put it into the AWS CLI yourself in the next step; I run commands using your
> locally-configured credentials, I don't need to see the keys.

---

## 4. Turn on billing protection (free, ~3 min)

1. Account menu → **Billing and Cost Management**.
2. **Billing preferences** → enable **"Receive AWS Free Tier alerts"** and enter
   your email.
3. **Budgets** → **Create budget** → template **"Zero spend budget"** *or* a
   **Monthly cost budget** of **USD 5**, alert at 80% and 100% to your email.
   This emails you the moment anything starts to cost money.

---

## 5. Install the AWS CLI + Terraform locally

```bash
brew install awscli terraform
aws --version        # expect aws-cli/2.x
terraform -version   # expect Terraform v1.x
```

---

## 6. Configure the AWS CLI with your admin keys

Run this **yourself** and paste the keys from step 3 when prompted:

```bash
aws configure
# AWS Access Key ID     : <paste>
# AWS Secret Access Key : <paste>
# Default region name   : sa-east-1
# Default output format : json
```

Verify it works:

```bash
aws sts get-caller-identity
```

You should see your account ID and the `arca-admin` user ARN. ✅

---

## 7. Give me two non-secret values

Once the above is done, tell me:

1. Your **12-digit AWS account ID** (from `aws sts get-caller-identity` — not secret).
2. Confirm the **region** (`sa-east-1`, or another if you prefer).

That's all I need to write and run the Terraform. The domain (NIC.ar → Route 53)
comes later in Phase 5 — you don't need it yet.

---

## What happens next (so you know the shape)

With the CLI configured, **I** will (via Terraform, using your local creds):
- create the **ECR** repo, **VPC security groups**, **EC2 `t3.micro`** + Elastic IP,
  **RDS PostgreSQL `db.t4g.micro`**, **SSM** parameters, and the **GitHub OIDC role**;
- you'll review the `terraform plan` before anything is created;
- nothing is applied without your go-ahead.

You will **not** need to click around the console creating servers — these
prerequisites (account, root MFA, admin user, billing alarm, CLI) are the only
manual parts.
