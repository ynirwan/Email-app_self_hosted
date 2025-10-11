import logging, smtplib
from datetime import datetime
from fastapi import HTTPException
from bson import ObjectId
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template

from database import (
    get_campaigns_collection,
    get_settings_collection,
    get_subscribers_collection,
    get_templates_collection,
    get_email_logs_collection,
    get_audit_collection,
)

logger = logging.getLogger(__name__)

# ----------------- Helpers -----------------

async def get_smtp_settings():
    settings = await get_settings_collection().find_one({"type": "email"})
    if not settings or not settings.get("config"):
        raise HTTPException(status_code=404, detail="SMTP not configured")
    cfg = settings["config"]
    return {
        "smtp_server": cfg.get("smtp_server"),
        "smtp_port": cfg.get("smtp_port", 587),
        "username": cfg.get("username"),
        "password": cfg.get("password"),
    }

async def log_email(campaign_id, recipient, success, message):
    logs = get_email_logs_collection()
    audit = get_audit_collection()
    doc = {
        "type": "test_email",
        "campaign_id": campaign_id,
        "recipient": recipient,
        "success": success,
        "message": message,
        "timestamp": datetime.utcnow(),
    }
    await logs.insert_one(doc)
    await audit.insert_one({**doc, "action": f"test_email_{'sent' if success else 'failed'}"})

def personalize(text: str, subscriber: dict = None):
    if not subscriber:
        subscriber = {"name": "Test User", "email": "test@example.com"}
    try:
        return Template(text).render(
            subscriber=subscriber,
            name=subscriber.get("name","Test User"),
            email=subscriber.get("email","test@example.com"),
            first_name=subscriber.get("name","Test").split()[0],
        )
    except Exception:
        return text

async def get_subscriber_data(list_id=None, subscriber_id=None):
    subs = get_subscribers_collection()
    if subscriber_id:
        q = {"_id": ObjectId(subscriber_id)} if ObjectId.is_valid(subscriber_id) else {"_id": subscriber_id}
        return await subs.find_one(q)
    if list_id:
        return await subs.find_one({"list": list_id})
    return await subs.find_one({"status": "active"})

async def build_email(campaign: dict, recipient: str, subscriber=None):
    subject = personalize(campaign.get("subject","No Subject"), subscriber)

    msg = MIMEMultipart("alternative")
    sender_email = campaign.get("sender_email")
    sender_name = campaign.get("sender_name") or "Sender"
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient
    if campaign.get("reply_to"): msg["Reply-To"] = campaign["reply_to"]
    msg["Subject"] = f"[TEST] {subject}"

    html_content = subject
    if campaign.get("template_id") and ObjectId.is_valid(campaign["template_id"]):
        tpl = await get_templates_collection().find_one({"_id": ObjectId(campaign["template_id"])})
        if tpl: html_content = tpl.get("content_json",{}).get("html", html_content)
    html_content = personalize(html_content, subscriber)

    msg.attach(MIMEText(html_content,"html"))
    return msg

async def send_email(campaign, recipient, subscriber=None):
    smtp = await get_smtp_settings()
    msg = await build_email(campaign, recipient, subscriber)
    try:
        server = smtplib.SMTP(smtp["smtp_server"], smtp["smtp_port"], timeout=10)
        server.starttls()
        server.login(smtp["username"], smtp["password"])
        server.sendmail(campaign.get("sender_email"), recipient, msg.as_string())
        server.quit()
        return True,"sent"
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        return False,str(e)

# ----------------- Public API -----------------

async def send_test_email(campaign_id: str, test_email: str, use_custom_data=False, list_id=None, subscriber_id=None):
    campaigns = get_campaigns_collection()
    if not ObjectId.is_valid(campaign_id):
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    subscriber = None
    if use_custom_data:
        subscriber = await get_subscriber_data(list_id, subscriber_id)

    success, msg = await send_email(campaign, test_email, subscriber)
    await log_email(campaign_id, test_email, success, msg)

    if not success:
        raise HTTPException(status_code=500, detail=msg)
    return {"message": f"Test email sent to {test_email}", "status":"sent"}

