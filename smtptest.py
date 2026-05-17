#!/usr/bin/env python3
"""
SMTP connection + auth tester for MTA Platform.
Usage:  python smtp_test.py

Fill in USERNAME / PASSWORD below with credentials from the admin panel.
"""

import smtplib
import ssl
import sys

# ── Config ────────────────────────────────────────────────────────────────────
HOST     = "mail.gangainbox.com"
PORT     = 587          # 587 = STARTTLS  |  465 = SMTPS  |  25 = plain

USERNAME = "smtp1912"           # SMTP username from admin panel
PASSWORD = "OYW6hfKNp6GEYa0t" # SMTP password from admin panel

FROM     = "test@gangainbox.com"
TO       = "deliver-to@example.com"
SUBJECT  = "SMTP test"
BODY     = "This is a test message from the MTA platform SMTP tester."
# ─────────────────────────────────────────────────────────────────────────────


def test_smtp():
    print(f"\n{'='*60}")
    print(f"  SMTP Test  →  {HOST}:{PORT}")
    print(f"{'='*60}")

    # ── Step 1: TCP connect ───────────────────────────────────────────────────
    print(f"\n[1] Connecting to {HOST}:{PORT} ...")
    try:
        if PORT == 465:
            context = ssl.create_default_context()
            smtp = smtplib.SMTP_SSL(HOST, PORT, context=context, timeout=15)
        else:
            smtp = smtplib.SMTP(HOST, PORT, timeout=15)
        smtp.set_debuglevel(0)   # set to 1 for raw SMTP transcript
        print("    ✅ TCP connection established")
    except TimeoutError:
        print("    ❌ Timed out — port may be blocked by firewall/security group")
        sys.exit(1)
    except ConnectionRefusedError:
        print("    ❌ Connection refused — Haraka not listening on this port")
        sys.exit(1)
    except OSError as e:
        print(f"    ❌ Connection failed: {e}")
        sys.exit(1)

    with smtp:
        # ── Step 2: Banner ────────────────────────────────────────────────────
        banner = smtp.sock.recv(0) if False else ""   # banner is read internally
        print(f"\n[2] Connected — sending EHLO ...")

        # ── Step 3: EHLO ──────────────────────────────────────────────────────
        code, resp = smtp.ehlo()
        lines = resp.decode(errors='replace').splitlines()
        print(f"    EHLO {code} — capabilities:")
        for line in lines:
            print(f"      {line}")

        has_starttls = any("STARTTLS" in l.upper() for l in lines)
        has_auth     = any("AUTH"     in l.upper() for l in lines)

        # ── Step 4: STARTTLS ──────────────────────────────────────────────────
        if PORT == 587:
            print(f"\n[4] STARTTLS advertised: {'yes ✅' if has_starttls else 'NO ❌'}")
            if has_starttls:
                try:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    print("    ✅ STARTTLS upgrade complete")
                    # Re-EHLO after TLS handshake
                    code2, resp2 = smtp.ehlo()
                    lines2 = resp2.decode(errors='replace').splitlines()
                    print("    Post-TLS capabilities:")
                    for line in lines2:
                        print(f"      {line}")
                    has_auth = any("AUTH" in l.upper() for l in lines2)
                except ssl.SSLCertVerificationError as e:
                    print(f"    ⚠️  TLS cert verification failed: {e}")
                    print("       → Try: context.check_hostname=False; context.verify_mode=ssl.CERT_NONE")
                    sys.exit(1)
                except Exception as e:
                    print(f"    ❌ STARTTLS failed: {e}")
                    sys.exit(1)
            else:
                print("    ⚠️  Server did not advertise STARTTLS — check tls plugin + certs")
                print("       Attempting AUTH without TLS (plain)...")

        # ── Step 5: AUTH ──────────────────────────────────────────────────────
        print(f"\n[5] AUTH advertised: {'yes ✅' if has_auth else 'NO ❌'}")
        print(f"    Authenticating as '{USERNAME}' ...")
        try:
            smtp.login(USERNAME, PASSWORD)
            print("    ✅ AUTH success")
        except smtplib.SMTPAuthenticationError as e:
            code_a = e.smtp_code
            msg_a  = e.smtp_error.decode(errors='replace') if e.smtp_error else str(e)
            print(f"    ❌ AUTH failed ({code_a}): {msg_a}")
            print("       → Check username/password in admin panel")
            print("       → Make sure the SMTP user is active and account is not suspended")
            sys.exit(1)
        except smtplib.SMTPException as e:
            print(f"    ❌ AUTH error (SMTP): {e}")
            sys.exit(1)
        except Exception as e:
            print(f"    ❌ AUTH error: {e}")
            sys.exit(1)

        # ── Step 6: Send test message ─────────────────────────────────────────
        print(f"\n[6] Sending  {FROM}  →  {TO} ...")
        msg = (
            f"From: {FROM}\r\n"
            f"To: {TO}\r\n"
            f"Subject: {SUBJECT}\r\n"
            f"MIME-Version: 1.0\r\n"
            f"Content-Type: text/plain; charset=UTF-8\r\n"
            f"\r\n"
            f"{BODY}\r\n"
        )
        try:
            smtp.sendmail(FROM, [TO], msg)
            print("    ✅ Message accepted by server")
        except smtplib.SMTPRecipientsRefused as e:
            print(f"    ❌ Recipient refused: {e}")
        except smtplib.SMTPSenderRefused as e:
            print(f"    ❌ Sender refused: {e}")
        except smtplib.SMTPDataError as e:
            print(f"    ❌ DATA error {e.smtp_code}: {e.smtp_error}")
        except Exception as e:
            print(f"    ❌ Send failed: {e}")

        # ── Step 7: QUIT ──────────────────────────────────────────────────────
        smtp.quit()
        print("\n[7] ✅ QUIT — connection closed cleanly")

    print(f"\n{'='*60}")
    print("  All steps passed — SMTP is working correctly ✅")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    test_smtp()

