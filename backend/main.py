# ========================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import auth, subscribers, campaigns, stats, setting, templates, domains,  analytics, email_settings
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s: %(asctime)s - %(message)s",
)

app = FastAPI(debug=True)

# ✅ Fixed CORS - Allow both development ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # React dev server default
        "http://localhost:5173",   # Vite dev server default
        "http://localhost:4173",   # Vite preview default
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Fixed router includes - removed duplication
app.include_router(auth.router, prefix="/api/auth")
app.include_router(subscribers.router, prefix="/api/subscribers")
app.include_router(campaigns.router, prefix="/api")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(setting.router, prefix="/api/settings", tags=["items"])
app.include_router(templates.router, prefix="/api/templates")  # ✅ Fixed: single include
app.include_router(domains.router, prefix="/api/domains")       # ✅ Fixed: proper prefix
app.include_router(analytics.router, prefix="/api/analytics")  # ✅ Added analytics router
app.include_router(email_settings.router, prefix="/api/email")

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Log all registered routes for debugging
if __name__ == "__main__":
    for route in app.routes:
        print(f"{route.path} → {route.methods}")
