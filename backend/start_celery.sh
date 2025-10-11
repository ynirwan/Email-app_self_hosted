#!/bin/bash
# start_celery.sh - Script to start Celery workers for email campaigns

echo "Starting Celery workers for high-volume email processing..."

# Start email workers (for individual email sending)
echo "Starting email workers..."
celery -A tasks.email_campaign_tasks.celery_app worker \
    --loglevel=info \
    --queues=email_queue \
    --concurrency=8 \
    --hostname=email-worker@%h \
    --detach

# Start batch workers (for batch processing)
echo "Starting batch workers..."
celery -A tasks.email_campaign_tasks.celery_app worker \
    --loglevel=info \
    --queues=batch_queue \
    --concurrency=4 \
    --hostname=batch-worker@%h \
    --detach

# Start campaign workers (for campaign management)
echo "Starting campaign workers..."
celery -A tasks.email_campaign_tasks.celery_app worker \
    --loglevel=info \
    --queues=campaign_queue \
    --concurrency=2 \
    --hostname=campaign-worker@%h \
    --detach

# Start Flower for monitoring
echo "Starting Flower monitoring..."
celery -A tasks.email_campaign_tasks.celery_app flower \
    --port=5555 \
    --detach

echo "All Celery workers started!"
echo "Monitor at: http://localhost:5555"
echo ""
echo "To stop all workers run: pkill -f celery"
