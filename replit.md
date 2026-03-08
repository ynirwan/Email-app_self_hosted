# Email Marketing Application - Complete Setup

## ✅ Application Status
- **Backend**: Running on port 8000 ✅
- **Frontend**: Running on port 5000 ✅
- **Celery Worker**: Running ✅
- **Celery Beat**: Running ✅
- **MongoDB Atlas**: Connected ✅
- **Redis Labs**: Connected ✅

## System Architecture

### Backend (FastAPI) - Port 8000
- **Database**: MongoDB Atlas
  - Connection: `mongodb+srv://email_user:xwyKRgNI7BCY7C5j@cluster0.bvsh4b5.mongodb.net/email_marketing`
- **Cache/Queue Broker**: Redis Labs
  - Connection: `redis://default:6ozcn1aIV5IEojt1jcVrc3XBwTuAvaYg@redis-10202.c10.us-east-1-2.ec2.cloud.redislabs.com:10202/0`
- **Features**: 166 routes, Full production-ready setup
- **Health Check**: ✅ READY (all systems connected)

### Frontend (React + Vite) - Port 5000
- **Build Tool**: Vite v5.4.21
- **Styling**: Tailwind CSS
- **API Configuration**: Environment-variable driven
- **Multi-Host Support**: Automatically detects Replit dev environments

### Background Workers (Celery)
- **Worker**: Processing tasks with 4 concurrent processes
- **Beat Scheduler**: Scheduling periodic tasks
- **Broker**: Redis Labs (external)

## Frontend API Configuration

### How It Works
The frontend `api.js` uses a 3-tier priority system:

**Priority 1: Environment Variable (Recommended for multiple hosts)**
```javascript
VITE_API_BASE_URL=https://your-backend-api-url.com/api
```

**Priority 2: Auto-detection (Replit environments)**
- Automatically detects `replit.dev` domain
- Constructs backend URL: `protocol://hostname:8000/api`
- Works across all Replit fork environments

**Priority 3: Fallback (Development)**
- Falls back to `http://localhost:8000/api`

### Configuration Files
- **`.env`** - Current environment variables (gitignored)
- **`.env.example`** - Template with all available options

### Setup for Multiple Hosts

**For Replit Pike environment:**
```
VITE_API_BASE_URL=https://5474f674-6074-4eb8-8818-15946bef35a1-00-1y8lhfj74gqcq.pike.replit.dev:8000/api
```

**For Replit Picard environment:**
```
VITE_API_BASE_URL=https://1e3e51b5-d74b-43fc-9d8d-5d25ea6cb6c7-00-3fzv7fuo5ld08.picard.replit.dev/api
```

**For Production:**
```
VITE_API_BASE_URL=https://your-production-domain.com/api
```

## Environment Variables

### Backend (.env)
```
ENVIRONMENT=development
MONGODB_URI=mongodb+srv://email_user:xwyKRgNI7BCY7C5j@cluster0.bvsh4b5.mongodb.net/email_marketing
REDIS_URL=redis://default:6ozcn1aIV5IEojt1jcVrc3XBwTuAvaYg@redis-10202.c10.us-east-1-2.ec2.cloud.redislabs.com:10202/0
MASTER_ENCRYPTION_KEY=p_5hyFfKYwJ03G1R-m74_cFFQlJh_YXQxAh_VdsNiKQ=
```

### Frontend (.env)
```
VITE_API_BASE_URL=http://localhost:8000/api
```

## Workflows

The `.replit` file defines 3 workflows:

1. **Frontend** - Vite dev server on port 5000
2. **Backend** - FastAPI on port 8000
3. **Celery Worker** - Background task processor with beat scheduler

Local MongoDB and Redis services are NOT used (external services configured).

## Quick Start

### Development (Local)
```bash
# Frontend
cd email-app/frontend && npm run dev

# Backend
cd email-app/backend && uvicorn main:app --host 0.0.0.0 --port 8000

# Celery
cd email-app/backend && celery -A celery_app worker --beat
```

### Replit
- All workflows are configured in `.replit` file
- Frontend auto-detects backend on Replit environments
- Or set `VITE_API_BASE_URL` in frontend/.env for explicit control

## Key Files
- `email-app/backend/.env` - Backend configuration
- `email-app/backend/core/config.py` - Settings management
- `email-app/backend/celery_app.py` - Celery setup
- `email-app/frontend/.env` - Frontend API URL configuration
- `email-app/frontend/src/api.js` - API client with multi-host support
- `email-app/frontend/vite.config.js` - Build configuration
- `email-app/.replit` - Workflow definitions

## Status Summary
✅ **Production Ready** - All services configured and running
✅ **External Services** - MongoDB Atlas and Redis Labs connected
✅ **Multi-Host Support** - Frontend works across different Replit environments
✅ **Environment Variable Driven** - Easy to reconfigure for different deployments
