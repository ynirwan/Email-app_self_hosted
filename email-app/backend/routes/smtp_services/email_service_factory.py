from core.security import decrypt_password
from .base_email_service import BaseEmailService
from .ses_email_service import SESEmailService
from .smtp_email_service import SMTPEmailService


def get_email_service(settings_doc) -> BaseEmailService:
    """
    Takes a settings document and returns an appropriate email service instance.
    """
    if not settings_doc:
        raise Exception("SMTP settings missing")

    config = settings_doc['config']
    smtp_choice = config.get('smtp_choice')
    provider = config.get('provider')
    smtp_server = config.get('smtp_server')

    # --- If need boto3 IAM access in future, uncomment this block and comment the SMTP one ---
    '''
    if smtp_choice == 'client' and provider == 'amazonses':
        aws_access_key = config.get('username')
        encrypted_secret = config.get('password')
        aws_secret_key = decrypt_password(encrypted_secret)
        return SESEmailService(
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key
        )
    '''

    # --- Use Amazon SES via SMTP ---
    if smtp_choice == 'client' and provider == 'amazonses':
        return SESEmailService(
            smtp_server=config.get("smtp_server", "email-smtp.ap-south-1.amazonaws.com"),
            smtp_port=config.get("smtp_port", 587),
            username=config.get("username"),
            password=decrypt_password(config.get("password"))
        )

    elif smtp_choice == 'managed' or provider == 'managed_service':
        encrypted_password = config.get('password')
        password = decrypt_password(encrypted_password) if encrypted_password else None
        return SMTPEmailService(
            smtp_server=smtp_server,
            smtp_port=config.get('smtp_port', 587),
            username=config.get('username'),
            password=password
        )
    else:
        raise Exception("Unsupported SMTP configuration")


def get_email_service_sync(settings_collection):
    """
    Synchronously fetch SMTP config document and return email service.
    For use with sync MongoDB collections (PyMongo).
    """
    settings_doc = settings_collection.find_one({'type': 'email_smtp'})
    return get_email_service(settings_doc)

