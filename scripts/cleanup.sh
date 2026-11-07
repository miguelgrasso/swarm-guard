#!/usr/bin/env bash
# cleanup.sh — Delete the swarm-guard CloudFormation stack and verify no orphan resources remain.
#
# Usage:
#   ENV=dev bash scripts/cleanup.sh
#   ENV=prod bash scripts/cleanup.sh
#
# Required environment variables:
#   ENV   — deployment environment (dev | prod); maps to stack name swarm-guard-${ENV}
#
# Required tools: aws CLI configured with credentials for us-east-2

set -euo pipefail

REGION="us-east-2"
ENV="${ENV:?ENV environment variable must be set (dev | prod)}"
STACK_NAME="swarm-guard-${ENV}"

echo "==> Deleting CloudFormation stack: ${STACK_NAME} in ${REGION}"
aws cloudformation delete-stack \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo "==> Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"
echo "    Stack deleted."

echo ""
echo "==> Verifying no orphan resources remain..."

PASS=0
FAIL=0

check_resource() {
    local resource_type="$1"
    local check_cmd="$2"
    local description="$3"

    if eval "${check_cmd}" > /dev/null 2>&1; then
        echo "  FAIL: ${description} still exists"
        FAIL=$((FAIL + 1))
    else
        echo "  PASS: ${description} removed"
        PASS=$((PASS + 1))
    fi
}

# IAM Roles
for agent in researcher analyst writer; do
    ROLE_NAME="swarm-guard-${ENV}-${agent}-role"
    check_resource "IAM Role" \
        "aws iam get-role --role-name '${ROLE_NAME}' --region ${REGION} 2>/dev/null" \
        "IAM Role ${ROLE_NAME}"
done

# CloudWatch Log Groups
for agent in researcher analyst writer; do
    LOG_GROUP="/swarm-guard/${ENV}/${agent}"
    check_resource "Log Group" \
        "aws logs describe-log-groups --log-group-name-prefix '${LOG_GROUP}' --region ${REGION} \
         --query 'logGroups[?logGroupName==\`${LOG_GROUP}\`]' --output text | grep -q ." \
        "Log Group ${LOG_GROUP}"
done

# CloudWatch Alarm
ALARM_NAME="swarm-guard-${ENV}-budget-alarm"
check_resource "CloudWatch Alarm" \
    "aws cloudwatch describe-alarms --alarm-names '${ALARM_NAME}' --region ${REGION} \
     --query 'MetricAlarms[0]' --output text | grep -q PASS" \
    "CloudWatch Alarm ${ALARM_NAME}"

echo ""
echo "==> Cleanup verification complete: ${PASS} PASS, ${FAIL} FAIL"

if [ "${FAIL}" -gt 0 ]; then
    echo "    WARNING: ${FAIL} resource(s) may still exist. Check the AWS Console."
    exit 1
fi

echo "    All resources verified clean."
exit 0
