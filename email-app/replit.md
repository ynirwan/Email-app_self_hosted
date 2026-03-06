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
- `ab_testing.py` - Independent A/B testing system (separated from campaigns)

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
- **Two-file config architecture**:
  - `backend/core/config.py` — App-level settings (DB, Redis, JWT, CORS, security, deployment, uploads, API). Instantiates `settings`.
  - `backend/tasks/task_config.py` — Task/Celery-specific settings (batch sizes, retries, timeouts, rate limits, DLQ, monitoring, analytics, queues, feature flags). Instantiates `task_settings`.
  - All other files import from these two — no direct `os.getenv` calls elsewhere.
  - Email/SMTP/SES provider settings are managed via frontend UI and stored in MongoDB, not in env vars.
- **python-dotenv**: Environment variable management via `backend/.env`.
- **Fernet (cryptography)**: Encryption for sensitive configuration values like SMTP passwords.

### HTTP/Async
- **httpx/aiohttp**: Async HTTP clients for external API calls.
- **aioredis**: Async Redis operations.

### Logging
- **Centralized file logging** in `var/log/` directory with rotating file handlers:
  - `app.log` - All application logs from every module (routes, tasks, database, middleware, uvicorn)
  - `error.log` - Error-level logs only for quick troubleshooting
  - `access.log` - HTTP request/response access logs
  - `celery.log` - Celery worker task logs
  - `celery_error.log` - Celery error-only logs
- Log rotation: 10MB per file, 5 backups kept
- Console output also preserved for live monitoring

## Recent Changes (2026-02-28)
- **Configuration Consolidation**: Refactored all backend config into two clean files
  - `backend/core/config.py` — App-level settings only (DB, Redis, JWT, CORS, security, deployment)
  - `backend/tasks/task_config.py` — Task/Celery settings only (batch sizes, retries, timeouts, rate limits, DLQ, monitoring)
  - Removed all `os.getenv` calls from every other file (database.py, celery_app.py, auth.py, security.py, all tasks, all routes, main.py)
  - Removed unused email/SMTP/SES env vars (EMAIL_PROVIDER, AWS_*, SES_*, DEFAULT_SENDER_*, SMTP_MODE, etc.) — these are managed via frontend UI/database
  - Removed redundant REDIS_HOST/REDIS_PORT (REDIS_URL is sufficient)
  - Cleaned up `.env` to only contain actively-used variables with clear section comments

- **Unsubscribe System**: Unique unsubscribe tokens per email send, public GET/POST endpoints for unsubscribe processing, `{{unsubscribe_url}}` template variable, `List-Unsubscribe` email header support
  - Route: `backend/routes/unsubscribe.py` - Token generation, GET `/api/unsubscribe/{token}` (HTML page), POST `/api/webhooks/unsubscribe` (JSON webhook)
  - Config: `UNSUBSCRIBE_DOMAIN` env var (default: `gnagainbox.com`)
  - DB collection: `unsubscribe_tokens` (async + sync getters in database.py)
- **Campaign Scheduling**: Schedule campaigns for future send, cancel scheduled campaigns
  - Endpoints: POST `/api/campaigns/{id}/schedule`, POST `/api/campaigns/{id}/cancel-schedule`
  - Celery beat task: `check_scheduled_campaigns` runs every minute to trigger due campaigns
  - UI: Schedule modal with date/time picker, scheduled status badge, cancel schedule action
- **Template Editor**: Enhanced unsubscribe link button visibility across all editor modes (visual, HTML, drag-drop)

## Previous Changes (2026-02-21)
- Added list dropdown with dynamic field loading to Add Subscriber modal
- Fixed horizontal scrolling in SubscriberListView (sidebar-aware layout constraints)
- Auto-cleanup of completed upload jobs (5-min server-side cleanup, frontend filters completed)
- Comprehensive file-based logging to var/log/ with app, error, access, and celery logs
- Backend endpoint: GET /subscribers/lists/{list_name}/fields for per-list field discovery