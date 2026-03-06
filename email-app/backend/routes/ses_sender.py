# utils/email_sender.py
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict
import re
from fastapi import HTTPException, status

# Initialize SES client
ses_client = boto3.client("ses", region_name="us-east-1")

# simple regex for email format check
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# fake in-memory quota store (replace with DB in SaaS)
tenant_quota_usage = {}

def send_email_via_ses(
    tenant_id: str,
    sender: str,
    recipients: List[str],
    subject: str,
    body_html: str,
    body_text: str = "",
    test_mode: bool = False
) -> Dict:
    """
    Send email via AWS SES with pre-checks for SaaS multi-tenant.
    """

    # 1. Tenant check
    if not tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid tenant")

    # 2. Sender validation (must be SES verified)
    # SES enforces this, but check at panel level too
    if not EMAIL_REGEX.match(sender):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid sender format")

    # 3. Recipient validation
    valid_recipients = []
    for r in recipients:
        if EMAIL_REGEX.match(r):
            valid_recipients.append(r)
    if not valid_recipients:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No valid recipients")

    # 4. Test mode restriction
    if test_mode:
        # allow only whitelisted test addresses
        valid_recipients = [r for r in valid_recipients if r.endswith("@example.com")]
        if not valid_recipients:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Test mode blocked for these recipients")

    # 5. Quota check
    usage = tenant_quota_usage.get(tenant_id, 0)
    daily_limit = 200  # example per-tenant cap
    if usage + len(valid_recipients) > daily_limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Quota exceeded")

    # 6. Content validation
    if not subject.strip() or not body_html.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Subject and body required")
    if len(body_html.encode("utf-8")) > 10 * 1024 * 1024:  # 10MB SES max
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email body too large")

    # 7. Attempt send
    try:
        response = ses_client.send_email(
            Source=sender,
            Destination={"ToAddresses": valid_recipients},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text or subject, "Charset": "UTF-8"},
                    "Html": {"Data": body_html, "Charset": "UTF-8"}
                }
            }
        )
    except ClientError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"SES error: {e.response['Error']['Message']}")

    # 8. Update quota + log
    tenant_quota_usage[tenant_id] = usage + len(valid_recipients)

    return {
        "MessageId": response["MessageId"],
        "Recipients": valid_recipients,
        "QuotaUsed": tenant_quota_usage[tenant_id]
    }

