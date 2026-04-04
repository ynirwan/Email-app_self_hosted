import smtplib

SMTP_HOST = "host.docker.internal"
SMTP_PORT = 587
SMTP_USERNAME = "testuser"
SMTP_PASSWORD = "testpass"

server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
server.set_debuglevel(1)
server.ehlo()

if not server.has_extn("starttls"):
    raise RuntimeError("Server does not support STARTTLS")

server.starttls()
server.ehlo()
server.login(SMTP_USERNAME, SMTP_PASSWORD)
print("SMTP login successful")
server.quit()
