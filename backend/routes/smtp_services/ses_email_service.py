# backend/routes/smtp_services/ses_email_service.py
from typing import Optional
from .base_email_service import BaseEmailService, EmailResult
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from .base_email_service import BaseEmailService, EmailResult
import re


logger = logging.getLogger(__name__)

class SESEmailService(BaseEmailService):
    def __init__(self, smtp_server=None, smtp_port=587, username=None, password=None,
                 aws_access_key=None, aws_secret_key=None, region='ap-south-1'):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def send_email(self, sender_email, recipient_email, subject, html_content,
                   sender_name=None, reply_to=None):

        try:
            # Prepare email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
            msg['To'] = recipient_email

            if reply_to:
                msg['Reply-To'] = reply_to

            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            message_id = None

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)

                # Use low-level SMTP commands to capture the final response
                server.mail(sender_email)
                server.rcpt(recipient_email)

                # Send DATA command and capture response containing MessageId
                code, response = server.data(msg.as_bytes())

                # Extract MessageId from response
                message_id = self._extract_message_id(code, response)

                # Always log the SMTP response for debugging
                logger.info("SES_SMTP_FINAL_RESPONSE", extra={
                    "campaign": "debug",
                    "recipient": recipient_email,
                    "smtp_code": code,
                    "smtp_response": response.decode('utf-8') if isinstance(response, bytes) else str(response),
                    "extracted_message_id": message_id,
                    "message_id_found": message_id is not None
                })

            # Return result with MessageId
            return self._create_result(True, message_id, None)

        except smtplib.SMTPException as e:
            logger.error("SMTP_ERROR", extra={
                "error": str(e),
                "recipient": recipient_email
            })
            return self._create_result(False, None, f"SMTP Error: {str(e)}")

        except Exception as e:
            logger.exception("EMAIL_SEND_EXCEPTION", extra={
                "error": str(e),
                "recipient": recipient_email
            })
            return self._create_result(False, None, str(e))

    def _extract_message_id(self, code, response):
        """Extract MessageId from SES SMTP response"""
        try:
            if code != 250:
                return None

            response_text = response.decode('utf-8') if isinstance(response, bytes) else str(response)

            # SES SMTP returns format: "250 Ok MessageId"
            # Try multiple patterns to capture the MessageId
            patterns = [
                r'250\s+Ok\s+([a-zA-Z0-9\-_\.]+)',  # Most common: "250 Ok MessageId"
                r'Ok\s+([a-zA-Z0-9\-_\.]+)',        # Alternative: "Ok MessageId"
                r'250.*?([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}-[a-f0-9]{6})',  # UUID pattern
                r'250.*?([a-zA-Z0-9\-_]{20,})',     # Generic long alphanumeric string
            ]

            for i, pattern in enumerate(patterns):
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    logger.info("MESSAGE_ID_EXTRACTED", extra={
                        "pattern_used": i,
                        "pattern": pattern,
                        "full_response": response_text,
                        "message_id": match.group(1)
                    })
                    return match.group(1)

            # If no pattern matches, log the full response for analysis
            logger.warning("MESSAGE_ID_NOT_FOUND", extra={
                "full_response": response_text,
                "response_length": len(response_text)
            })

            return None

        except Exception as e:
            logger.error("MESSAGE_ID_EXTRACTION_ERROR", extra={
                "error": str(e),
                "response": str(response)
            })
            return None

    def _create_result(self, success, message_id, error):
        """Create a standardized result object"""
        return type('EmailResult', (), {
            'success': success,
            'message_id': message_id,
            'error': error
        })()










#if need to used boto in future 
#    Amazon SES service using boto instead of smtp.

'''
class SESEmailService(BaseEmailService):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = 'us-east-1'):
        import boto3
        import time
        import logging
        from botocore.exceptions import ClientError

        self.logger = logging.getLogger(__name__)
        self.ses_client = boto3.client(
            'ses',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region
        )
        self.region = region
        self.rate_limit = 14  # SES limit: 14 emails per second
        self.last_send_time = 0
        self.ClientError = ClientError
        self.time = time

    def send_email(self, sender_email, recipient_email, subject, html_content,
                   text_content=None, sender_name=None, reply_to=None) -> EmailResult:
        current_time = self.time.time()
        time_diff = current_time - self.last_send_time
        if time_diff < (1.0 / self.rate_limit):
            self.time.sleep((1.0 / self.rate_limit) - time_diff)

        try:
            source = f"{sender_name} <{sender_email}>" if sender_name else sender_email
            destination = {'ToAddresses': [recipient_email]}
            message = {
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {'Data': html_content, 'Charset': 'UTF-8'}
                }
            }
            if text_content:
                message['Body']['Text'] = {'Data': text_content, 'Charset': 'UTF-8'}
            reply_to_addresses = [reply_to] if reply_to else []

            response = self.ses_client.send_email(
                Source=source,
                Destination=destination,
                Message=message,
                ReplyToAddresses=reply_to_addresses
            )
            self.last_send_time = self.time.time()

            return EmailResult(success=True, message_id=response['MessageId'], recipient=recipient_email)

        except self.ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            self.logger.error(f"SES Error for {recipient_email}: {error_code} - {error_message}")
            return EmailResult(success=False, error=f"{error_code}: {error_message}", recipient=recipient_email)

        except Exception as e:
            self.logger.error(f"Unexpected error for {recipient_email}: {str(e)}")
            return EmailResult(success=False, error=str(e), recipient=recipient_email)
'''
