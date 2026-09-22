# Nightly SQLite backup target.
# A systemd timer on the instance uploads a consistent copy of app.db here each
# night. The DB is a few MB and objects expire after 30 days, so storage cost is
# a few cents/month — negligible against the $15 budget. (The budget auto-stop
# targets EC2; S3 is not stopped, but its cost here is immaterial.)
resource "aws_s3_bucket" "backups" {
  bucket = "${var.project}-db-backups-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${var.project}-db-backups" }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"
    filter {
      prefix = "backups/"
    }
    expiration {
      days = 30
    }
  }
}

# Allow the instance role to write backups (scoped to the backups/ prefix).
resource "aws_iam_role_policy" "ec2_s3_backup" {
  name = "${var.project}-s3-backup"
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${aws_s3_bucket.backups.arn}/backups/*"
    }]
  })
}

output "backup_bucket" {
  description = "S3 bucket holding nightly SQLite backups."
  value       = aws_s3_bucket.backups.bucket
}
