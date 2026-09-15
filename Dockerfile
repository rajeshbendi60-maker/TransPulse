FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn Flask-Migrate psycopg2-binary Flask-Limiter Flask-Cors Flask-Compress

# Copy the application
COPY . .

# Expose port 5000 for internal Docker network routing
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Run with Gunicorn (4 workers binding to 0.0.0.0:5000)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]

