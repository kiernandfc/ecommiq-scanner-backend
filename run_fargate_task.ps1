# PowerShell script to run ECS Fargate task

# Set variables
$SUBNET_ID = "subnet-3ccbc210"
$SECURITY_GROUP_ID = "sg-00531a449f8e40e5d"
$CLUSTER_NAME = "ecommiq-cluster"
$TASK_DEFINITION_NAME = "ecommiq-scanner"
$VPC_ID = "vpc-d746b4af"

# Echo configuration
Write-Host "Using the following configuration:" -ForegroundColor Yellow
Write-Host "  VPC ID: $VPC_ID"
Write-Host "  Subnet ID: $SUBNET_ID"
Write-Host "  Security Group ID: $SECURITY_GROUP_ID"
Write-Host "  Cluster: $CLUSTER_NAME"
Write-Host "  Task Definition: $TASK_DEFINITION_NAME"
Write-Host ""

# Create cluster if it doesn't exist
Write-Host "Creating cluster if it doesn't exist..." -ForegroundColor Yellow
try {
    $clusterExists = aws ecs describe-clusters --clusters $CLUSTER_NAME | ConvertFrom-Json
    if ($clusterExists.clusters.Count -eq 0) {
        Write-Host "Creating new cluster: $CLUSTER_NAME" -ForegroundColor Green
        aws ecs create-cluster --cluster-name $CLUSTER_NAME
    } else {
        Write-Host "Cluster already exists: $CLUSTER_NAME" -ForegroundColor Green
    }
}
catch {
    Write-Host "Creating new cluster: $CLUSTER_NAME" -ForegroundColor Green
    aws ecs create-cluster --cluster-name $CLUSTER_NAME
}

# Run the task
Write-Host "Starting Fargate task..." -ForegroundColor Yellow
$networkConfig = "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}"

try {
    $result = aws ecs run-task `
        --cluster $CLUSTER_NAME `
        --task-definition $TASK_DEFINITION_NAME `
        --network-configuration $networkConfig `
        --launch-type FARGATE `
        --count 1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Task started successfully!" -ForegroundColor Green
    } else {
        Write-Host "Error starting task. Exit code: $LASTEXITCODE" -ForegroundColor Red
    }
}
catch {
    Write-Host "Error starting task: $_" -ForegroundColor Red
}

Write-Host "Command executed. Check AWS console for task status." -ForegroundColor Yellow
