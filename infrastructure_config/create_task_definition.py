import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Get the parent directory path for .env file
parent_dir = str(Path(__file__).parent.parent.absolute())

# Load environment variables from .env in parent directory
load_dotenv(os.path.join(parent_dir, '.env'))

# Create task definition
task_def = {
    "family": "ecommiq-scanner",
    "networkMode": "awsvpc",
    "executionRoleArn": "arn:aws:iam::387663585850:role/ecsTaskExecutionRole",
    "taskRoleArn": "arn:aws:iam::387663585850:role/ecsTaskRole",
    "containerDefinitions": [
        {
            "name": "ecommiq-scanner-container",
            "image": "387663585850.dkr.ecr.us-east-1.amazonaws.com/ecommiq-scanner:latest",
            "essential": True,
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": "/ecs/ecommiq-scanner",
                    "awslogs-region": "us-east-1",
                    "awslogs-stream-prefix": "ecs"
                }
            },
            "environment": []
        }
    ],
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "1024",
    "memory": "2048"
}

# Add environment variables
env_file_path = os.path.join(parent_dir, '.env')
try:
    with open(env_file_path, 'r') as env_file:
        env_content = env_file.read()
        
    for key, value in os.environ.items():
        # Only add variables that were in .env, not system variables
        if key in env_content:
            task_def["containerDefinitions"][0]["environment"].append({
                "name": key,
                "value": value
            })
except FileNotFoundError:
    print(f"Warning: .env file not found at {env_file_path}")

# Write to file
with open('task-definition.json', 'w') as f:
    json.dump(task_def, f, indent=2)

print("Task definition created from .env variables")