# backend/routes/smtp_services/__init__.py
from .base_email_service import BaseEmailService, EmailResult
from .ses_email_service import SESEmailService
from .smtp_email_service import SMTPEmailService
from .email_service_factory import get_email_service, get_email_service_sync
from .email_campaign_processor import SyncEmailCampaignProcessor

__all__ = [
    'BaseEmailService',
    'EmailResult',
    'SESEmailService', 
    'SMTPEmailService',
    'get_email_service',
    'get_email_service_sync',
    'SyncEmailCampaignProcessor'
]
