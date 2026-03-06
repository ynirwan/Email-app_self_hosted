# Use Python 3.11 slim image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' fastapi \
    && chown -R fastapi:fastapi /app
USER fastapi

# Expose port
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["bash", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers $(nproc)"]
