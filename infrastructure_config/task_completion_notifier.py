import boto3
import os
import json
import datetime
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    """
    Lambda function that sends an email notification when an ECS task completes or fails.
    It retrieves and includes the CloudWatch logs from the task.
    """
    # Parse the ECS task event
    print("Received event:", json.dumps(event))
    
    try:
        # Get detail type to check if this is a task state change event
        detail_type = event.get('detail-type')
        if detail_type != 'ECS Task State Change':
            print(f"Ignoring non-ECS task state change event: {detail_type}")
            return
            
        task_arn = event['detail']['taskArn']
        cluster_arn = event['detail']['clusterArn']
        last_status = event['detail']['lastStatus']
        desired_status = event['detail'].get('desiredStatus', '')
        
        # Only send notification when task reaches STOPPED state
        if last_status != 'STOPPED':
            print(f"Task not yet completed, current status: {last_status}")
            return
            
        # Extract task ID from ARN
        task_id = task_arn.split('/')[-1]
        cluster_name = cluster_arn.split('/')[-1]
        
        # Get container info to find the log stream
        ecs = boto3.client('ecs')
        task_details = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=[task_id]
        )
        
        # Check if there was a container
        if not task_details['tasks'] or not task_details['tasks'][0].get('containers'):
            raise Exception(f"No containers found for task {task_id}")
            
        # Get container details
        container = task_details['tasks'][0]['containers'][0]
        container_name = container['name']
        exit_code = container.get('exitCode')
        container_status = "SUCCESS" if exit_code == 0 else "FAILED"
        reason = container.get('reason', 'No reason provided')
        
        # Get task started and stopped time
        started_at = task_details['tasks'][0].get('startedAt')
        stopped_at = task_details['tasks'][0].get('stoppedAt')
        
        if started_at and stopped_at:
            # Calculate duration
            start_time = datetime.datetime.fromtimestamp(started_at.timestamp())
            end_time = datetime.datetime.fromtimestamp(stopped_at.timestamp())
            duration = end_time - start_time
            duration_str = str(duration)
        else:
            duration_str = "Unknown"
        
        # Determine log stream name - We now know the exact format used by Fargate
        log_group_name = f"/ecs/ecommiq-scanner"
        
        # Set the log stream name according to the known format
        # Format is: ecs/container-name/task-id
        log_stream_name = f"ecs/{container_name}/{task_id}"
        print(f"Using log stream name: {log_stream_name}")
        
        # As a fallback, search for the log stream if the direct naming doesn't work
        logs_client = boto3.client('logs')
        try:
            # Check if the log stream exists first
            try:
                # Just a quick check to see if the stream exists
                logs_client.get_log_stream(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name
                )
                print(f"Confirmed log stream exists: {log_stream_name}")
            except Exception as e:
                # If the stream doesn't exist with our format, search for it
                print(f"Direct log stream not found: {str(e)}")
                
                # List log streams matching the task ID
                response = logs_client.describe_log_streams(
                    logGroupName=log_group_name,
                    logStreamNamePrefix=task_id,
                    limit=1
                )
                
                if response.get('logStreams'):
                    log_stream_name = response['logStreams'][0]['logStreamName']
                    print(f"Found log stream via task ID: {log_stream_name}")
                else:
                    print(f"No log stream found with task ID: {task_id}")
            
        except Exception as e:
            print(f"Error finding log stream: {str(e)}")
            # Continue with the original log stream name as a best effort
        
        # Fetch logs from CloudWatch (logs_client already initialized above)
        try:
            log_events = logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=log_stream_name,
                limit=10000  # Adjust based on expected log volume
            )
            
            # Format logs in reverse order (newest first)
            formatted_logs = []
            for event in log_events['events']:
                timestamp = datetime.datetime.fromtimestamp(event['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
                formatted_logs.append(f"[{timestamp}] {event['message']}")
            
            # Reverse the log entries so newest is at the top
            formatted_logs.reverse()
            log_output = "\n".join(formatted_logs)
        except ClientError as e:
            log_output = f"Error retrieving logs: {str(e)}"
        
        # Prepare email content
        sns_client = boto3.client('sns')
        subject = f"ECS Task {container_status}: {container_name} ({task_id})"
        
        message = f"""
Task Execution Summary
---------------------
Task: {task_id}
Container: {container_name}
Status: {container_status}
Exit Code: {exit_code}
Reason: {reason}
Duration: {duration_str}
Started: {start_time.strftime('%Y-%m-%d %H:%M:%S') if started_at else 'Unknown'}
Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S') if stopped_at else 'Unknown'}

Log Output:
-----------
{log_output}
        """
        
        # Send email notification via SNS
        sns_client.publish(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Subject=subject,
            Message=message
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Notification sent successfully')
        }
    except Exception as e:
        print(f"Error processing task completion: {str(e)}")
        # Send error notification
        sns_client = boto3.client('sns')
        sns_client.publish(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Subject=f"Error processing ECS task notification",
            Message=f"An error occurred while processing ECS task completion notification: {str(e)}\n\nEvent: {json.dumps(event)}"
        )
        raise
