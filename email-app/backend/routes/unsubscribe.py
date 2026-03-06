import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from bson import ObjectId

from database import (
    get_unsubscribe_tokens_collection,
    get_subscribers_collection,
    get_suppressions_collection,
)
from core.config import settings

router = APIRouter(tags=["unsubscribe"])
logger = logging.getLogger(__name__)


def generate_unsubscribe_token(campaign_id: str, subscriber_id: str, email: str) -> str:
    token = uuid.uuid4().hex
    from database import get_sync_unsubscribe_tokens_collection
    col = get_sync_unsubscribe_tokens_collection()
    col.insert_one({
        "token": token,
        "campaign_id": campaign_id,
        "subscriber_id": subscriber_id,
        "email": email,
        "created_at": datetime.utcnow(),
        "used": False,
    })
    return token


def build_unsubscribe_url(token: str) -> str:
    domain = settings.UNSUBSCRIBE_DOMAIN
    return f"https://{domain}/api/unsubscribe/{token}"


class UnsubscribeWebhookPayload(BaseModel):
    token: str


UNSUBSCRIBE_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribed</title>
    <style>
        body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
        .card { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
        h1 { color: #333; font-size: 24px; }
        p { color: #666; line-height: 1.6; }
        .check { font-size: 48px; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="check">&#10003;</div>
        <h1>Successfully Unsubscribed</h1>
        <p>You have been removed from our mailing list and will no longer receive emails from us.</p>
    </div>
</body>
</html>"""

UNSUBSCRIBE_ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribe Error</title>
    <style>
        body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
        .card { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
        h1 { color: #cc0000; font-size: 24px; }
        p { color: #666; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Invalid Link</h1>
        <p>This unsubscribe link is invalid or has already been used. If you continue to receive unwanted emails, please contact us directly.</p>
    </div>
</body>
</html>"""


async def _process_unsubscribe(token: str) -> dict:
    tokens_col = get_unsubscribe_tokens_collection()
    subscribers_col = get_subscribers_collection()
    suppressions_col = get_suppressions_collection()

    token_doc = await tokens_col.find_one({"token": token})
    if not token_doc or token_doc.get("used"):
        return {"success": False, "reason": "invalid_token"}

    email = token_doc["email"]
    subscriber_id = token_doc["subscriber_id"]
    campaign_id = token_doc["campaign_id"]

    await tokens_col.update_one(
        {"token": token},
        {"$set": {"used": True, "used_at": datetime.utcnow()}}
    )

    await subscribers_col.update_many(
        {"email": email},
        {"$set": {
            "status": "unsubscribed",
            "unsubscribed_at": datetime.utcnow(),
            "is_suppressed": True,
        }}
    )

    existing = await suppressions_col.find_one({"email": email, "type": "unsubscribe"})
    if not existing:
        await suppressions_col.insert_one({
            "email": email,
            "type": "unsubscribe",
            "reason": "user_unsubscribed",
            "source": "unsubscribe_link",
            "campaign_id": campaign_id,
            "subscriber_id": subscriber_id,
            "scope": "global",
            "created_at": datetime.utcnow(),
        })

    logger.info(f"Unsubscribe processed for {email} (campaign: {campaign_id})")
    return {"success": True, "email": email}


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_via_link(token: str):
    result = await _process_unsubscribe(token)
    if result["success"]:
        return HTMLResponse(content=UNSUBSCRIBE_SUCCESS_HTML, status_code=200)
    return HTMLResponse(content=UNSUBSCRIBE_ERROR_HTML, status_code=400)


@router.post("/webhooks/unsubscribe")
async def unsubscribe_webhook(payload: UnsubscribeWebhookPayload):
    result = await _process_unsubscribe(payload.token)
    if result["success"]:
        return {"status": "success", "message": f"Unsubscribed {result['email']}"}
    raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe token")
