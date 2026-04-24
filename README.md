Email Marketing Platform

A self-hosted email marketing platform built with FastAPI (backend) and React + Vite (frontend).

It supports:

Email campaigns
Subscriber and list management
Automation workflows
Audience segmentation
A/B testing
Analytics and tracking
Multiple email sending providers (AWS SES / SMTP)

The platform uses MongoDB for storage, Redis for caching and queuing, and Celery for background processing.

Features
Create and send email campaigns
Manage subscriber lists with bulk CSV import
Build automation workflows
Segment audiences with filters
Run A/B tests
Track campaign performance and analytics
Handle bounces, complaints, unsubscribes, and suppressions
Use AWS SES or custom SMTP providers
Schedule campaigns for future sending
Tech Stack
Backend
FastAPI
Motor (async MongoDB)
PyMongo (sync DB access for Celery tasks)
Celery
Redis
JWT authentication
bcrypt / passlib
Frontend
React
Vite
Tailwind CSS
Axios
React Router
Recharts
React Quill
PapaParse
Lucide React
Project Architecture
Backend (FastAPI)

The backend follows an async-first architecture using FastAPI and Motor for API operations, while Celery tasks use synchronous DB access where appropriate.

Main API Route Modules

Located in backend/routes/:

campaigns.py — Campaign CRUD and sending
subscribers.py — Subscriber management and bulk upload
automation.py — Automation workflows
segments.py — Audience segmentation
templates.py — Email templates
analytics.py / stats.py — Reporting and metrics
webhooks.py — AWS SES bounce/complaint handling
suppressions.py — Suppression list management
ab_testing.py — Standalone A/B testing system
Background Jobs (Celery)

Celery handles long-running and asynchronous tasks such as:

Campaign batch sending
Automation execution
A/B test processing
Analytics aggregation
Suppression processing
Scheduled campaign checks
Important

Celery workers are not started automatically in Replit.

You must run them manually or create a workflow for:

celery -A celery_app worker --loglevel=info

Redis is used as the Celery broker and result backend.

Subscriber Data Model

Subscribers use a three-tier field system:

1. Universal Fields

Always available:

email
status
timestamps
2. Standard Fields

Common optional fields:

first_name
last_name
phone
company
3. Custom Fields

User-defined key/value fields stored dynamically.

Email Sending System

The platform uses a provider abstraction layer for sending email.

Supported Providers
AWS SES (SMTP or API)
Custom SMTP
Managed SMTP (for hosted use cases)
Key Components
email_service_factory.py — Provider selection and abstraction
rate_limiter.py — Sending rate limits
Suppression filtering before delivery
Built-in Protections
Per-minute limits
Per-hour limits
Per-day limits
Suppression list checks for:
bounces
complaints
unsubscribes
Automation Workflows

The automation engine supports trigger-based email sequences.

Supported Capabilities
Subscription triggers
Cart abandonment triggers
Custom event triggers
Delays (hours / days / weeks)
Conditional branching
Timezone-aware scheduling
Trigger Flow
Subscription events are triggered from routes/subscribers.py
Custom/e-commerce events are triggered from routes/events.py
Processing logic lives in tasks/automation_tasks.py

Automation execution checks:

subscriber status
suppression state
frequency caps
A/B Testing

A/B testing is implemented as a separate system from campaign sending.

It has:

dedicated routes
Celery queue support
expiry checks
background execution flow
Configuration

The project uses a two-file configuration architecture.

App Settings

backend/core/config.py

Handles:

database config
Redis config
JWT/auth settings
CORS
security settings
uploads
deployment settings
API config

Instantiates:

settings
Task / Celery Settings

backend/tasks/task_config.py

Handles:

batch sizes
retries
timeouts
task rate limits
DLQ settings
monitoring
analytics settings
queue config
feature flags

Instantiates:

task_settings
Configuration Rules
All files should import from these two config files
No direct os.getenv() calls elsewhere
Email provider credentials/settings are stored in MongoDB and managed via the frontend UI
Environment Variables

Environment variables are loaded from:

backend/.env

Using:

python-dotenv
Sensitive Data

Sensitive values such as SMTP passwords are encrypted using:

cryptography / Fernet
Database and Infrastructure
MongoDB

Primary datastore for:

campaigns
subscribers
templates
analytics
automation data
audit logs
unsubscribe tokens
Redis

Used for:

Celery broker/backend
caching
rate limiting
background coordination
Flower

Used for Celery monitoring.

Authentication

Authentication is handled with:

JWT tokens (python-jose)
Password hashing (bcrypt, passlib)
Logging

The application uses centralized file-based logging under:

var/log/
Log Files
app.log — All application logs
error.log — Error-level logs only
access.log — HTTP access logs
celery.log — Celery worker logs
celery_error.log — Celery errors only
Log Rotation
10 MB per file
5 backups retained

Console logging is also preserved for live monitoring.


This app talks to relay/submission SMTPs — SES, SendGrid, Mailgun, custom SMTP servers — not to recipient mail servers. So the error space is completely different from what I described before.
Let me reframe correctly.

Correct Error Space — Relay/Submission SMTP Only
When you submit to SES/SendGrid/Mailgun/custom SMTP, the errors you get back are about your relationship with that relay — not about the recipient's mailbox. The relay accepts the message and handles delivery itself.
