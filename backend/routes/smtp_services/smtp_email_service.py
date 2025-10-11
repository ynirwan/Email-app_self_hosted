# backend/routes/smtp_services/smtp_email_service.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from .base_email_service import BaseEmailService, EmailResult  # Fixed import

class SMTPEmailService(BaseEmailService):
    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str, use_tls: bool = True):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send_email(self, sender_email: str, recipient_email: str, subject: str,
                   html_content: str, text_content: Optional[str] = None,
                   sender_name: Optional[str] = None, reply_to: Optional[str] = None) -> EmailResult:
        try:
            msg = MIMEMultipart("alternative")
            from_header = f"{sender_name} <{sender_email}>" if sender_name else sender_email
            msg["From"] = from_header
            msg["To"] = recipient_email
            msg["Subject"] = subject
            if reply_to:
                msg.add_header('reply-to', reply_to)

            if text_content:
                part1 = MIMEText(text_content, "plain")
                msg.attach(part1)
            part2 = MIMEText(html_content, "html")
            msg.attach(part2)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(sender_email, [recipient_email], msg.as_string())

            return EmailResult(success=True, message_id=None, recipient=recipient_email)

        except Exception as e:
            return EmailResult(success=False, error=str(e), recipient=recipient_email)
