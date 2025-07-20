# PowerShell script to build Docker image and push to ECR
# Simplified version with minimal formatting to avoid syntax issues

param(
    [string]$ImageTag = "latest",
    [string]$ECRRepository = "387663585850.dkr.ecr.us-east-1.amazonaws.com/ecommiq-scanner",
    [string]$Region = "us-east-1"
)

# Set error handling
$ErrorActionPreference = "Stop"

Write-Host "=== EcommiQ Scanner - Docker Build & ECR Push ==="
Write-Host "Repository: $ECRRepository"
Write-Host "Tag: $ImageTag"
Write-Host "Region: $Region"
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..."

# Check Docker
try {
    Get-Command docker -ErrorAction Stop | Out-Null
    Write-Host "Docker found"
}
catch {
    Write-Host "ERROR: Docker is not installed or not in PATH"
    exit 1
}

# Check AWS CLI
try {
    Get-Command aws -ErrorAction Stop | Out-Null
    Write-Host "AWS CLI found"
}
catch {
    Write-Host "ERROR: AWS CLI is not installed or not in PATH"
    exit 1
}

# Check files
if (-not (Test-Path "Dockerfile")) {
    Write-Host "ERROR: Dockerfile not found in current directory"
    exit 1
}

if (-not (Test-Path "requirements.txt")) {
    Write-Host "ERROR: requirements.txt not found in current directory"
    exit 1
}

Write-Host "Files found"
Write-Host ""

# Step 1: Build Docker image
Write-Host "Step 1: Building Docker image..."
$LocalImageName = "ecommiq-scanner:$ImageTag"

try {
    docker build -t $LocalImageName .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed"
    }
    Write-Host "Docker image built successfully: $LocalImageName"
}
catch {
    Write-Host "ERROR: Failed to build Docker image"
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host ""

# Step 2: Authenticate Docker to ECR
Write-Host "Step 2: Authenticating Docker to ECR..."

try {
    $ECRDomain = $ECRRepository.Split('/')[0]
    aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $ECRDomain
    if ($LASTEXITCODE -ne 0) {
        throw "ECR authentication failed"
    }
    Write-Host "Successfully authenticated to ECR"
}
catch {
    Write-Host "ERROR: Failed to authenticate to ECR"
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host ""

# Step 3: Tag image for ECR
Write-Host "Step 3: Tagging image for ECR..."
$ECRImageName = "$ECRRepository`:$ImageTag"

try {
    docker tag $LocalImageName $ECRImageName
    if ($LASTEXITCODE -ne 0) {
        throw "Docker tag failed"
    }
    Write-Host "Image tagged for ECR: $ECRImageName"
}
catch {
    Write-Host "ERROR: Failed to tag image for ECR"
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host ""

# Step 4: Push image to ECR
Write-Host "Step 4: Pushing image to ECR..."

try {
    docker push $ECRImageName
    if ($LASTEXITCODE -ne 0) {
        throw "Docker push failed"
    }
    Write-Host "Image pushed successfully to ECR!"
}
catch {
    Write-Host "ERROR: Failed to push image to ECR"
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host ""

# Step 5: Clean up local images (optional)
Write-Host "Step 5: Cleaning up local images..."
try {
    docker rmi $LocalImageName -f
    Write-Host "Local image cleaned up"
}
catch {
    Write-Host "Warning: Could not clean up local image (this is not critical)"
}

Write-Host ""
Write-Host "=== BUILD AND PUSH COMPLETED SUCCESSFULLY ==="
Write-Host "ECR Image URI: $ECRImageName"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Update your task definition to use: $ECRImageName"
Write-Host "2. Run your Fargate task with the updated configuration"
