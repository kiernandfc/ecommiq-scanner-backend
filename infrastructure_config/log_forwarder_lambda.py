import base64
import gzip
import json
import boto3
import os

def lambda_handler(event, context):
    # Get the SNS topic ARN from environment variables
    sns_topic_arn = os.environ['SNS_TOPIC_ARN']
    
    # Initialize SNS client
    sns = boto3.client('sns')
    
    # CloudWatch Logs data is base64 encoded and compressed
    decoded_payload = base64.b64decode(event['awslogs']['data'])
    uncompressed_payload = gzip.decompress(decoded_payload)
    log_data = json.loads(uncompressed_payload)
    
    # Extract log information
    log_group = log_data['logGroup']
    log_stream = log_data['logStream']
    log_events = log_data['logEvents']
    
    # Prepare the email content
    subject = f"ECS Task Logs: {log_group}/{log_stream}"
    
    message_lines = [f"Log Group: {log_group}", f"Log Stream: {log_stream}", ""]
    
    # Add each log event to the message
    for event in log_events:
        timestamp = event['timestamp']
        message = event.get('message', '')
        message_lines.append(f"[{timestamp}] {message}")
    
    message = "\n".join(message_lines)
    
    # Publish to SNS
    sns.publish(
        TopicArn=sns_topic_arn,
        Subject=subject,
        Message=message
    )
    
    return {
        'statusCode': 200,
        'body': f"Successfully processed {len(log_events)} log events"
    }
