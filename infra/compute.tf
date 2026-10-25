# ── EC2 instance role ─────────────────────────────────────────────────────────

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.project}-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# SSM Session Manager (admin access without SSH) + ECR image pulls.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Read this project's SSM parameters (and decrypt SecureStrings).
data "aws_iam_policy_document" "ec2_ssm_read" {
  statement {
    sid     = "ReadAppParams"
    actions = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = [
      # GetParametersByPath authorizes against the path itself...
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}",
      # ...GetParameter(s) against the individual child parameters.
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*",
    ]
  }

  # Decrypt SecureString params, but only when accessed via SSM (so this isn't a
  # broad KMS grant). Avoids depending on the aws/ssm key existing at plan time.
  statement {
    sid       = "DecryptParams"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${data.aws_region.current.name}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "ec2_ssm_read" {
  name   = "${var.project}-ssm-read"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_ssm_read.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project}-ec2"
  role = aws_iam_role.ec2.name
}

# ── Instance ──────────────────────────────────────────────────────────────────

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  # 15 GB gp3 — ample for the OS + app image + SQLite DB + invoice images
  # (~200 MB), and cheaper than the old 30 GB.
  root_block_device {
    volume_size = 15
    volume_type = "gp3"
    encrypted   = true
  }

  # Install Docker + the compose plugin and prep the app directory.
  # ARCH is resolved at boot (uname -m → x86_64 or aarch64) so this works on
  # both x86 and Graviton instances.
  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    dnf update -y
    dnf install -y docker
    systemctl enable --now docker
    usermod -aG docker ec2-user
    mkdir -p /usr/local/lib/docker/cli-plugins
    ARCH=$(uname -m)
    curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$${ARCH}" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    mkdir -p /opt/${var.project}/data
  EOF

  user_data_replace_on_change = false

  tags = { Name = "${var.project}-app" }

  # The AMI data source tracks the latest AL2023 arm64 image, which changes over
  # time. Without this, a routine apply would destroy/recreate the running
  # instance (wiping the SQLite volume) just to adopt a newer AMI. Re-image
  # deliberately (remove this temporarily), not by accident.
  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-app" }
}
