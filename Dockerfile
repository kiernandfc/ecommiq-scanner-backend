# Use Python 3.12 as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables for better Python output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run the application
# Use ENTRYPOINT to allow passing arguments at runtime
ENTRYPOINT ["python", "main.py"]
# Default arguments if none are provided at runtime
CMD ["--progress", "--threads", "10"]
