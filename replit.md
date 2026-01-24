# Email Marketing Platform

## Overview

This is a self-hosted email marketing platform built with FastAPI (Python backend) and React (Vite frontend). The system enables users to manage email campaigns, subscriber lists, automation workflows, and analytics. It uses MongoDB for data persistence, Redis for caching and task queuing, and Celery for background job processing. The platform supports multiple email sending methods including AWS SES and custom SMTP configurations.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture (FastAPI)

**Core Framework**: FastAPI with async/await patterns throughout. The application uses Motor (async MongoDB driver) for database operations and supports both sync and async database access patterns for different use cases (API routes use async, Celery tasks use sync).

**Celery Integration**:
- The platform uses Celery for background tasks (email sending, automation, analytics).
- **Current Setup**: Celery workers are NOT running by default in the Replit environment. You must start them manually or add a new workflow to run `celery -A celery_app worker --loglevel=info`.
- **Redis**: Connected to an external Redis instance for brokering and results.

**API Structure**: Routes are organized by feature domain in `backend/routes/`:
- `campaigns.py` - Campaign CRUD and sending operations
- `subscribers.py` - Subscriber management with bulk upload support
- `automation.py` - Email automation workflows
- `segments.py` - Audience segmentation with 8 filter types
- `templates.py` - Email template management
- `analytics.py` & `stats.py` - Campaign performance metrics
- `webhooks.py` - AWS SES webhook handling for bounces/complaints
- `suppressions.py` - Email suppression list management

**Background Tasks**: Celery handles long-running operations:
- Email campaign batch sending
- A/B test execution
- Analytics aggregation
- Automation workflow execution
- Suppression list processing

**Three-Tier Field System**: Subscribers use a tiered field structure:
- Universal fields (email, status, timestamps) - always present
- Standard fields (first_name, last_name, phone, company) - common optional fields
- Custom fields - user-defined fields stored as key-value pairs

### Frontend Architecture (React + Vite)

**Build Tool**: Vite with React plugin for fast development and HMR.

**Styling**: Tailwind CSS for utility-first styling.

**Key Dependencies**:
- `react-router-dom` - Client-side routing
- `axios` - HTTP client for API calls
- `recharts` - Analytics charts and visualizations
- `react-quill` - Rich text editor for email content
- `lucide-react` - Icon library
- `papaparse` - CSV parsing for bulk subscriber imports

**State Management**: Component-level state with React hooks. API calls use axios with the backend running on the same host.

### Email Sending Architecture

**Multi-Provider Support**: The system abstracts email sending through a service factory pattern (`email_service_factory.py`), supporting:
- AWS SES (via SMTP or API)
- Custom SMTP servers
- Managed SMTP option for hosted deployments

**Rate Limiting**: Built-in rate limiter (`rate_limiter.py`) enforces per-minute, per-hour, and per-day sending limits to prevent provider throttling.

**Suppression Filtering**: Before sending, the system checks subscribers against suppression lists (bounces, complaints, unsubscribes) to maintain sender reputation.

### Automation System

**Workflow Engine**: Supports trigger-based email sequences with:
- Multiple trigger types (subscription, cart abandonment, custom events)
- Delay steps (hours, days, weeks)
- Conditional branching based on engagement
- Timezone-aware scheduling

**Trigger Logic**:
- **Subscription**: Triggered via `routes/subscribers.py` when a user is added.
- **Events**: Triggered via `routes/events.py` for e-commerce actions like `cart-abandoned`.
- **Processing**: Logic resides in `tasks/automation_tasks.py`, checking subscriber status, suppression lists, and frequency caps before execution.

**Event Tracking**: Dedicated events system for tracking user actions that can trigger automations.

## External Dependencies

### Database
- **MongoDB**: Primary data store for all application data (campaigns, subscribers, templates, analytics, audit logs). Uses Motor for async operations and PyMongo for sync Celery tasks.
- **Redis**: Used for Celery task broker/backend, caching stats, and rate limiting state.

### Task Queue
- **Celery**: Distributed task queue for background processing. Configured with multiple queues (campaigns, analytics, automation, ab_tests).
- **Flower**: Celery monitoring dashboard.

### Email Services
- **AWS SES**: Primary email sending service (via boto3 for API, smtplib for SMTP).
- **Custom SMTP**: Alternative for users with their own mail servers.

### Authentication
- **JWT**: Token-based authentication using python-jose.
- **bcrypt/passlib**: Password hashing.

### Configuration
- **python-dotenv**: Environment variable management.
- **Fernet (cryptography)**: Encryption for sensitive configuration values like SMTP passwords.

### HTTP/Async
- **httpx/aiohttp**: Async HTTP clients for external API calls.
- **aioredis**: Async Redis operations.