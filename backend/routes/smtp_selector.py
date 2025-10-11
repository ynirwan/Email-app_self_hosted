from backend.database import get_settings_collection
from fastapi import HTTPException

async def get_email_config():
    settings = await get_settings_collection().find_one({"type": "email"})
    if not settings or not settings.get("config"):
        raise HTTPException(status_code=404, detail="Email sending config not found")
    return settings["config"]

async def get_email_sending_option():
    config = await get_email_config()
    smtp_choice = config.get("smtp_choice")
    # Possible values: 'client', 'managed'
    return smtp_choice

async def get_smtp_settings():
    config = await get_email_config()
    if config.get("smtp_choice") != "client":
        raise HTTPException(status_code=400, detail="SMTP is not the selected sending method")
    return {
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 587),
        "username": config.get("username"),
        "password": config.get("password"),
    }

