#!/usr/bin/env bash
#
# Runs ON the EC2 box (via SSM). Renders .env from SSM Parameter Store, logs in
# to ECR, pulls the given image, and (re)starts the stack.
#
# Usage: deploy.sh <image_uri>
set -euo pipefail

IMAGE_URI="${1:?usage: deploy.sh <image_uri>}"
REGION="sa-east-1"
SSM_PREFIX="/arcainvoices/prod"
APP_DIR="/opt/arcainvoices"
ECR_REGISTRY="879366471813.dkr.ecr.sa-east-1.amazonaws.com"

cd "$APP_DIR"

echo "[deploy] rendering .env from SSM ($SSM_PREFIX)"
{
  echo "IMAGE_URI=${IMAGE_URI}"
  aws ssm get-parameters-by-path \
    --region "$REGION" --path "$SSM_PREFIX" --with-decryption --recursive \
    --query 'Parameters[].[Name,Value]' --output text \
  | while IFS=$'\t' read -r name value; do
      echo "$(basename "$name")=${value}"
    done
} > .env.tmp
mv .env.tmp .env
chmod 600 .env

echo "[deploy] logging in to ECR"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "[deploy] pulling ${IMAGE_URI} and starting stack"
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

echo "[deploy] pruning old images"
docker image prune -f >/dev/null 2>&1 || true

echo "[deploy] done"
