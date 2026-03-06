# Email Marketing App (Updated)

The application is now configured according to the user's specific environment requirements.

## Current Configuration
- **Backend Environment**: Configured via `email-app/backend/.env`
- **Databases**: Using external MongoDB Atlas and Redis Labs instances. Local MongoDB/Redis services have been disabled.
- **Frontend**: React application using `.jsx` files.

## Workflows
- **Backend**: FastAPI on port 8000
- **Frontend**: Vite on port 5000
- **Celery**: Background worker and beat scheduler running.

## Note on Connectivity
The backend uses external connection strings provided in the `.env` file. If connectivity issues occur, please verify the credentials and network access for these external clusters.
