import smtplib
from email.mime.text import MIMEText

# 🔧 Update with your SES credentials & settings
SMTP_SERVER = "email-smtp.ap-south-1.amazonaws.com"  # change region if needed
SMTP_PORT = 587
SMTP_USERNAME = "AKIAQ3EGWJOBZXHPPFJC"
SMTP_PASSWORD = "BEj16pCBp5JoQ0DLQkjEk+F9nAHDQa3WO277TD1+wLQG"

SENDER = "verified-sender@example.com"  # must be verified in SES (if in sandbox)
RECIPIENT = "verified-recipient@example.com"  # must also be verified if in sandbox

def test_ses_connection():
    try:
        print("Connecting to SES...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        print("✅ Authentication successful")

        # Create a test email
        msg = MIMEText("This is a test email from SES connection script.")
        msg["Subject"] = "SES Connection Test"
        msg["From"] = SENDER
        msg["To"] = RECIPIENT

        # Send email
        server.sendmail(SENDER, [RECIPIENT], msg.as_string())
        print(f"📨 Test email sent from {SENDER} to {RECIPIENT}")

        server.quit()
    except smtplib.SMTPAuthenticationError as e:
        print("❌ Authentication failed. Check SMTP username/password.")
        print(e)
    except Exception as e:
        print("❌ Connection or sending failed:", str(e))

if __name__ == "__main__":
    test_ses_connection()

