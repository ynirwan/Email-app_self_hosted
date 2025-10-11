# backend/routes/smtp_services/base_email_service.py
from typing import Optional
from dataclasses import dataclass

@dataclass
class EmailResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    recipient: Optional[str] = None

class BaseEmailService:
    def send_email(self, sender_email: str, recipient_email: str, subject: str,
                   html_content: str, text_content: Optional[str] = None,
                   sender_name: Optional[str] = None, reply_to: Optional[str] = None) -> EmailResult:
        raise NotImplementedError("send_email must be implemented by subclasses")
