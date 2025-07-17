import json
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

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
for key, value in os.environ.items():
    # Only add variables that were in .env, not system variables
    if key in open('.env').read():
        task_def["containerDefinitions"][0]["environment"].append({
            "name": key,
            "value": value
        })

# Write to file
with open('task-definition.json', 'w') as f:
    json.dump(task_def, f, indent=2)

print("Task definition created from .env variables")