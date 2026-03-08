#!/bin/bash
cd /home/runner/workspace/backend
celery -A celery_app worker --beat --loglevel=info --logfile=../var/log/celery.log --queues=campaigns,automation,recovery,ses_events,webhooks,subscribers,suppressions,dlq,monitoring,analytics,templates,cleanup,ab_tests
