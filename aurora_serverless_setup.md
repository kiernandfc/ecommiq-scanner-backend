# Setting Up AWS Aurora Serverless PostgreSQL for Your Application

This guide explains how to set up an AWS Aurora Serverless PostgreSQL database for use with your application.

## Creating an Aurora Serverless v2 Cluster

1. Log in to the AWS Management Console and navigate to the RDS service.

2. Click "Create database" and select the following options:
   - Choose "Standard create"
   - Engine type: "Amazon Aurora"
   - Edition: "Amazon Aurora PostgreSQL-Compatible Edition"
   - Capacity type: "Serverless v2"
   - PostgreSQL version: 13.x or later

3. Set database configuration:
   - DB cluster identifier: `ecommiq-postgres` (or your preferred name)
   - Master username: Choose a username
   - Master password: Create a secure password

4. Configure Serverless capacity:
   - Minimum ACUs: 0.5 (for minimum cost when idle)
   - Maximum ACUs: 4 (adjust based on your expected workload)

5. Connectivity settings:
   - VPC: Select your application VPC
   - Subnet group: Choose or create a subnet group
   - Public access: Typically "No" for security
   - VPC security group: Create or select a security group that allows PostgreSQL traffic (port 5432) from your application servers

6. Additional settings:
   - Initial database name: `ecommiq-scanner`
   - Encryption: Enabled (recommended)
   - Backup: Enable automatic backups
   - Monitoring: Enable Enhanced Monitoring if needed

7. Click "Create database"

## IAM Authentication (Optional but Recommended)

For enhanced security, you can use IAM authentication:

1. Enable IAM authentication when creating the cluster or modify it afterward.

2. Create an IAM policy allowing database connections:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "rds-db:connect"
         ],
         "Resource": [
           "arn:aws:rds-db:region:account-id:dbuser:cluster-resource-id/database-user"
         ]
       }
     ]
   }
   ```

3. Attach this policy to the IAM role used by your application.

4. Set `USE_IAM_AUTH=true` in your `.env` file.

## Application Configuration

Update your `.env` file with the Aurora Serverless connection details:

```
# PostgreSQL Configuration (for AWS Aurora Serverless)
POSTGRESQL_HOST=your-cluster-identifier.cluster-xxxxxxxxxxxx.region.rds.amazonaws.com
POSTGRESQL_PORT=5432
POSTGRESQL_DB=ecommiq-scanner
POSTGRESQL_USER=your_username
POSTGRESQL_PASSWORD=your_password  # Not needed if using IAM authentication

# Aurora Serverless specific settings
USE_IAM_AUTH=false  # Set to true if using IAM authentication
AURORA_RESUME_TIMEOUT=30
AURORA_MIN_CAPACITY=0.5
AURORA_MAX_CAPACITY=4

# Database Type
DATABASE_TYPE=postgresql
```

## Migrating from DynamoDB

To migrate your data from DynamoDB to Aurora Serverless PostgreSQL:

1. Ensure your `.env` file is configured with both DynamoDB and PostgreSQL settings.

2. Run the migration script:
   ```
   python migrate_to_postgres.py
   ```

3. Once migration is complete, set `DATABASE_TYPE=postgresql` in your `.env` file to use PostgreSQL as your primary database.

## Performance Optimization

- Aurora Serverless scales based on connection load. Configure connection pooling appropriately.
- Set minimum capacity units to at least 0.5 ACUs to minimize cold start time.
- Use the retry mechanism in the PostgreSQL database class to handle cold starts.
- Consider using Data API for Aurora Serverless for applications with infrequent database access.

## Cost Management

- Aurora Serverless charges based on ACU-hours used.
- Set appropriate minimum and maximum capacity values.
- For development environments, you can set `AURORA_MIN_CAPACITY=0` to allow scaling to zero when not in use.
- Monitor your usage in AWS Cost Explorer to optimize settings.

## Troubleshooting Connection Issues

If you're experiencing connection issues with Aurora Serverless, try these troubleshooting steps:

### 1. Test Your Connection

Run the connection test script to diagnose issues:
```
python test_postgres_connection.py
```

This will check environment variables, network connectivity, and PostgreSQL authentication.

### 2. Check Environment Variables

Make sure your `.env` file has correct connection details:
```
POSTGRESQL_HOST=your-aurora-endpoint.rds.amazonaws.com
POSTGRESQL_PORT=5432
POSTGRESQL_DB=ecommiq-scanner
POSTGRESQL_USER=username
POSTGRESQL_PASSWORD=password
```

The error `could not translate host name "None" to address` typically means your `POSTGRESQL_HOST` variable is not set correctly.

### 3. Check Network Connectivity

- Ensure your Aurora security group allows connections from your IP address.
- If you're connecting from a VPC, make sure the Aurora security group allows connections from the VPC CIDR block.
- If connecting from outside AWS, ensure Aurora is set to be publicly accessible.

### 4. Database Parameters

- Verify the database exists - you may need to create the database first.
- Check if the user has the correct permissions.
- Make sure the password is correct.

### 5. Aurora Serverless-Specific Issues

- If using Aurora Serverless v2, ensure you have set up the database properly with minimum capacity (usually 0.5 ACUs).
- Serverless DB can take time to wake up from zero capacity - our retry logic should handle this, but you might want to set `AURORA_MIN_CAPACITY=0.5` to avoid cold starts.
- If using IAM authentication, make sure the IAM role has the `rds-db:connect` permission.

### 6. Check Migration with Debug Mode

Run the migration with only connection checking:
```
python migrate_to_postgres.py --check-only
```

### 7. Aurora Console Checks

In the AWS console:
1. Go to RDS > Databases and check that your Aurora cluster is available (not paused).
2. Check the "Connectivity & security" tab to verify endpoint and port.
3. Look at "Monitoring" for CPU usage to confirm the database is responsive.

If all else fails, create a new Aurora instance with simplified settings to test basic connectivity. 