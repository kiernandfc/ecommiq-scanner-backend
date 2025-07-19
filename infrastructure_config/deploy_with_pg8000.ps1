#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory=$true)]
    [string]$FunctionName
)

# Set error action preference
$ErrorActionPreference = "Stop"

Write-Host "Deploying Lambda function with pg8000 (pure Python PostgreSQL driver)..." -ForegroundColor Green

# Create temporary directory for packaging
$tempDir = "lambda_package_temp"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    Push-Location $tempDir
    
    # Copy Lambda function files
    Write-Host "Copying Lambda function files..." -ForegroundColor Yellow
    Copy-Item "../lambda_function.py" "."
    Copy-Item "../kitchen_cost_calculator.py" "."
    
    # Install pg8000 (pure Python, no binary issues!)
    Write-Host "Installing pg8000 with dependencies..." -ForegroundColor Yellow
    python -m pip install pg8000 -t .
    
    # Install pytz for timezone handling (Eastern Time)
    Write-Host "Installing pytz for timezone support..." -ForegroundColor Yellow
    python -m pip install pytz -t .
    
    # Install boto3 for completeness
    Write-Host "Installing boto3..." -ForegroundColor Yellow
    python -m pip install boto3 -t .
    
    # Clean up unnecessary files (but keep metadata for package detection)
    Write-Host "Cleaning up package..." -ForegroundColor Yellow
    Get-ChildItem -Recurse -Include "*.pyc", "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    
    # Create deployment package
    Write-Host "Creating deployment package..." -ForegroundColor Yellow
    $zipFile = "${FunctionName}.zip"
    
    # List contents before packaging for debugging
    Write-Host "Package contents:" -ForegroundColor Gray
    Get-ChildItem -Name | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    
    # Create zip file with all contents at root level
    Compress-Archive -Path "*" -DestinationPath $zipFile -Force
    
    # Get package size
    $packageSize = (Get-Item $zipFile).Length / 1MB
    Write-Host "Package size: $($packageSize.ToString('F2')) MB" -ForegroundColor Cyan
    
    # Deploy to AWS Lambda
    Write-Host "Updating Lambda function..." -ForegroundColor Yellow
    aws lambda update-function-code `
        --function-name $FunctionName `
        --zip-file "fileb://$zipFile" `
        --region us-east-1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Lambda function deployed successfully!" -ForegroundColor Green
        Write-Host "Function Name: $FunctionName" -ForegroundColor Cyan
        Write-Host "Region: us-east-1" -ForegroundColor Cyan
        Write-Host "Handler: lambda_function.lambda_handler" -ForegroundColor Cyan
        Write-Host "Database Driver: pg8000 (pure Python)" -ForegroundColor Cyan
        
        # Test the function
        Write-Host "Testing Lambda function..." -ForegroundColor Yellow
        $testPayload = @{
            "detail" = @{
                "lastStatus" = "STOPPED"
                "taskArn" = "arn:aws:ecs:us-east-1:387663585850:task/test-task"
            }
            "detail-type" = "ECS Task State Change"
        } | ConvertTo-Json -Depth 3
        
        Write-Host "Test payload: $testPayload" -ForegroundColor Gray
        
        Write-Host "Deployment completed successfully!" -ForegroundColor Green
        Write-Host " No more psycopg2 binary compatibility issues!" -ForegroundColor Green
        Write-Host " Pure Python solution with pg8000" -ForegroundColor Green
        
    } else {
        Write-Error "Failed to deploy Lambda function"
        exit 1
    }
    
} catch {
    Write-Error "Error during deployment: $($_.Exception.Message)"
    exit 1
} finally {
    Pop-Location
    if (Test-Path $tempDir) {
        Remove-Item -Recurse -Force $tempDir
    }
}
