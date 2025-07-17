#!/bin/bash
set -e

echo "Initializing AWS resources in LocalStack..."

# Create S3 bucket for state management
echo "Creating S3 bucket for state management..."
awslocal s3 mb s3://aws-infra-manager-state-dev

# Create DynamoDB table for locking
echo "Creating DynamoDB table for locking..."
awslocal dynamodb create-table \
    --table-name aws-infra-manager-locks \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5

# Create CloudWatch log group
echo "Creating CloudWatch log group..."
awslocal logs create-log-group --log-group-name /aws-infra-manager/logs

# Create CloudWatch log stream
echo "Creating CloudWatch log stream..."
awslocal logs create-log-stream \
    --log-group-name /aws-infra-manager/logs \
    --log-stream-name application-logs

echo "AWS resources initialization complete!"