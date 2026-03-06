smtp_host = "host.docker.internal"
smtp_port = 587
username = "testuser"
password = "testpass"

import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Test email body")
msg["Subject"] = "SMTP Test"
msg["From"] = "sender@example.com"
msg["To"] = "receiver@example.com"

server = smtplib.SMTP(smtp_host, smtp_port)
server.ehlo()
server.starttls()
server.ehlo()
server.login(username, password)
server.sendmail(msg["From"], [msg["To"]], msg.as_string())
server.quit()

print("Email sent")

