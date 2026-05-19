#!/usr/bin/env python3
"""
ZeniPost Email Marketing Platform — Interactive Setup Wizard
============================================================
Run this once on a fresh Linux server to install and configure the platform.

Requirements on the host:
  • Python 3.8+
  • Docker + Docker Compose v2  (docker compose)
  • curl / wget  (for Let's Encrypt via certbot Docker image)
  • Port 80 and 443 open in firewall

Usage:
    python3 install.py                      # auto-locate license.json
    python3 install.py --license /path/to/license.json
    python3 install.py --reconfigure        # re-run config only (skip LE if certs exist)
    python3 install.py --create-user        # just create an additional admin user
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
import textwrap
import time
import urllib.request
from datetime import date, datetime
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Terminal colours (no third-party deps)
# ---------------------------------------------------------------------------

RESET   = "\033[0m"
BOLD    = "\033[1m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"
DIM     = "\033[2m"

def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"

def ok(msg: str)   -> None: print(f"  {c(GREEN,'✔')}  {msg}")
def err(msg: str)  -> None: print(f"  {c(RED,'✘')}  {msg}")
def warn(msg: str) -> None: print(f"  {c(YELLOW,'!')}  {msg}")
def info(msg: str) -> None: print(f"  {c(CYAN,'→')}  {msg}")
def step(msg: str) -> None: print(f"\n{c(BOLD+BLUE,'▶')} {c(BOLD, msg)}")


def banner() -> None:
    print(c(CYAN, r"""
 ______          _ ____           _
|__  /___ _ __ (_)  _ \ ___  ___| |_
  / // _ \ '_ \| | |_) / _ \/ __| __|
 / /|  __/ | | | |  __/ (_) \__ \ |_
/____\___|_| |_|_|_|   \___/|___/\__|
"""))
    print(c(BOLD, "  Email Marketing Platform — Self-Hosted Setup Wizard"))
    print(c(DIM,  "  Version 1.0  |  https://zenipost.com\n"))


# ---------------------------------------------------------------------------
# License helpers
# ---------------------------------------------------------------------------

PLAN_FEATURES: Dict[str, Dict[str, Any]] = {
    "starter": {
        "ab_testing": False,
        "automation": False,
        "deliverability_dashboard": False,
        "segmentation": True,
        "custom_smtp": True,
        "api_access": False,
        "audit_trail": True,
        "remote_db": False,
        "remote_redis": False,
        "max_users": 1,
        "max_subscribers": 10_000,
        "max_campaigns_per_month": 10,
    },
    "professional": {
        "ab_testing": True,
        "automation": True,
        "deliverability_dashboard": True,
        "segmentation": True,
        "custom_smtp": True,
        "api_access": True,
        "audit_trail": True,
        "remote_db": True,
        "remote_redis": True,
        "max_users": 1,
        "max_subscribers": -1,
        "max_campaigns_per_month": -1,
    },
    "enterprise": {
        "ab_testing": True,
        "automation": True,
        "deliverability_dashboard": True,
        "segmentation": True,
        "custom_smtp": True,
        "api_access": True,
        "audit_trail": True,
        "remote_db": True,
        "remote_redis": True,
        "max_users": -1,
        "max_subscribers": -1,
        "max_campaigns_per_month": -1,
    },
}

PLAN_LABELS = {
    "starter":      f"{c(WHITE,'Starter')}     — local DB/Redis, basic campaigns",
    "professional": f"{c(CYAN,'Professional')} — remote DB/Redis option, A/B testing, automation",
    "enterprise":   f"{c(YELLOW,'Enterprise')}   — all features, multi-user, unlimited",
}


def load_license(path: Path) -> Dict[str, Any]:
    if not path.exists():
        fatal(f"License file not found: {path}\n"
              f"  Copy license.example.json to license.json and fill in your details.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fatal(f"license.json is not valid JSON: {exc}")
    return data


def validate_license(data: Dict[str, Any]) -> Dict[str, Any]:
    """Returns merged feature dict or raises SystemExit."""
    sig = data.get("signature", "")
    if sig in ("", "REPLACE_WITH_ACTUAL_SIGNATURE_FROM_VENDOR"):
        warn("License has a placeholder signature — running in trial/dev mode.")
        warn("Features will use plan defaults. Obtain a real license from your vendor.")
    else:
        secret = os.getenv("LICENSE_SIGNING_SECRET", "")
        if secret:
            canonical = json.dumps(
                {k: v for k, v in data.items() if k not in ("signature", "_comment")},
                sort_keys=True, separators=(",", ":"),
            ).encode()
            expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig.lower()):
                fatal("License signature verification FAILED. The license.json file may "
                      "have been tampered with. Contact your vendor.")
            ok("License signature verified.")

    # Expiry
    expires_raw = data.get("expires_at", "9999-12-31")
    try:
        expires = date.fromisoformat(expires_raw)
    except ValueError:
        fatal(f"Invalid expires_at date in license: {expires_raw}")
    if date.today() > expires:
        fatal(f"Your license expired on {expires}. Please renew before installing.")
    days_left = (expires - date.today()).days
    if days_left <= 30:
        warn(f"License expires in {days_left} day(s) on {expires}. Plan to renew soon.")

    plan = data.get("plan", "starter").lower()
    if plan not in PLAN_FEATURES:
        fatal(f"Unknown plan '{plan}' in license. Valid: {list(PLAN_FEATURES.keys())}")

    base = dict(PLAN_FEATURES[plan])
    override = data.get("features", {})
    for k, v in override.items():
        if k in base and isinstance(base[k], bool) and isinstance(v, bool):
            base[k] = base[k] and v   # can only disable, not enable above plan cap
        else:
            base[k] = v

    return base


def show_plan_summary(data: Dict[str, Any], features: Dict[str, Any]) -> None:
    plan  = data.get("plan", "starter")
    issued_to = data.get("issued_to", "—")
    domain    = data.get("domain", "—")
    expires   = data.get("expires_at", "—")

    print(f"\n  {c(BOLD,'License details')}")
    print(f"  {'Plan:':<22} {c(BOLD+CYAN, plan.upper())}")
    print(f"  {'Licensed to:':<22} {issued_to}")
    print(f"  {'Domain:':<22} {domain}")
    print(f"  {'Expires:':<22} {expires}")

    print(f"\n  {c(BOLD,'Included features')}")
    feat_labels = {
        "ab_testing":             "A/B Testing",
        "automation":             "Automation workflows",
        "deliverability_dashboard": "Deliverability dashboard",
        "segmentation":           "Audience segmentation",
        "custom_smtp":            "Custom SMTP providers",
        "api_access":             "API access",
        "audit_trail":            "Audit trail",
        "remote_db":              "Remote MongoDB option",
        "remote_redis":           "Remote Redis option",
    }
    for key, label in feat_labels.items():
        val = features.get(key, False)
        symbol = c(GREEN, "✔") if val else c(DIM, "✘")
        print(f"  {symbol}  {label}")

    subs = features.get("max_subscribers", 0)
    subs_str = "Unlimited" if subs == -1 else f"{subs:,}"
    print(f"\n  {'Max subscribers:':<22} {subs_str}")


# ---------------------------------------------------------------------------
# System requirements
# ---------------------------------------------------------------------------

def check_requirements() -> None:
    step("Checking system requirements")
    issues: List[str] = []

    # Python version
    if sys.version_info < (3, 8):
        issues.append(f"Python 3.8+ required (got {sys.version})")
    else:
        ok(f"Python {sys.version.split()[0]}")

    # Docker
    r = _run(["docker", "--version"], capture=True, check=False)
    if r.returncode != 0:
        issues.append("Docker is not installed. Install from https://docs.docker.com/get-docker/")
    else:
        ok(r.stdout.strip().split("\n")[0])

    # Docker Compose v2 (docker compose)
    r2 = _run(["docker", "compose", "version"], capture=True, check=False)
    if r2.returncode != 0:
        issues.append("Docker Compose v2 not found. Install via: apt install docker-compose-plugin")
    else:
        ok(r2.stdout.strip().split("\n")[0])

    # curl (for certbot check)
    if shutil.which("curl") is None and shutil.which("wget") is None:
        warn("Neither curl nor wget found. Let's Encrypt check may not work.")

    # Port availability (quick check)
    for port in (80, 443):
        in_use = _port_in_use(port)
        if in_use:
            warn(f"Port {port} appears to be in use. Nginx / Let's Encrypt may fail.")
        else:
            ok(f"Port {port} is free")

    if issues:
        print()
        for i in issues:
            err(i)
        fatal("Please fix the above issues before continuing.")


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("0.0.0.0", port)) == 0


# ---------------------------------------------------------------------------
# Domain / subdomain configuration
# ---------------------------------------------------------------------------

def ask_domain(license_data: Dict[str, Any]) -> str:
    step("Domain configuration")

    licensed_domain = license_data.get("domain", "").strip()
    if not licensed_domain:
        fatal("License file has no 'domain' field. Cannot proceed.")

    print(f"\n  Your license is issued for domain: {c(BOLD+CYAN, licensed_domain)}")
    use_sub = _ask_yes_no(
        f"  Do you want to run on a subdomain of {licensed_domain}? (e.g. app.{licensed_domain})"
    )

    if use_sub:
        while True:
            sub = input(f"  Enter subdomain prefix (e.g. 'app' for app.{licensed_domain}): ").strip().lower()
            if sub and re.match(r'^[a-z0-9][a-z0-9\-]*$', sub):
                domain = f"{sub}.{licensed_domain}"
                break
            err("Invalid subdomain. Use lowercase letters, digits, and hyphens only.")
    else:
        domain = licensed_domain

    print(f"\n  {c(BOLD,'Target domain:')} {c(GREEN, domain)}")
    return domain


def check_dns(domain: str) -> bool:
    step(f"Checking DNS A record for {domain}")

    # Get server's public IP
    server_ip = _get_public_ip()
    if server_ip:
        info(f"This server's public IP: {c(BOLD, server_ip)}")
    else:
        warn("Could not determine this server's public IP automatically.")
        server_ip = input("  Enter this server's public IP address: ").strip()

    # Resolve domain
    info(f"Resolving {domain} ...")
    try:
        resolved_ip = socket.gethostbyname(domain)
        if resolved_ip == server_ip:
            ok(f"{domain} → {resolved_ip}  ✔ matches server IP")
            return True
        else:
            warn(f"{domain} resolves to {resolved_ip}, but server IP is {server_ip}")
            warn("DNS is not pointed at this server yet.")
    except socket.gaierror:
        warn(f"Could not resolve {domain} — DNS may not have propagated yet.")

    print(f"\n  {c(YELLOW,'Action required:')}")
    print(f"  Create an A record in your DNS provider:")
    print(f"    {c(BOLD, domain)} → {c(BOLD, server_ip or '<this server IP>')}")
    print(f"  DNS changes can take up to 24h to propagate.\n")
    return _ask_yes_no("  Continue anyway? (SSL setup may fail if DNS is not ready)")


def _get_public_ip() -> Optional[str]:
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ):
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                ip = resp.read().decode().strip()
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                    return ip
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

def ask_mongodb(features: Dict[str, Any]) -> Tuple[str, bool]:
    """Returns (mongo_uri, is_local)."""
    step("MongoDB configuration")
    allows_remote = features.get("remote_db", False)

    if not allows_remote:
        info("Your plan includes local MongoDB only.")
        info("A MongoDB container will be started as part of this installation.")
        return "", True   # URI built later with generated password

    print(f"\n  {c(BOLD,'Options:')}")
    print(f"  1. {c(GREEN,'Local')} — run MongoDB in Docker on this server (recommended for single-server)")
    print(f"  2. {c(CYAN,'Remote')} — use an external MongoDB URI (Atlas, managed service, etc.)")
    choice = _ask_choice("Choose MongoDB setup", ["1", "2"])

    if choice == "1":
        return "", True
    else:
        print("\n  Enter your MongoDB URI.")
        print(f"  Example: {c(DIM,'mongodb+srv://user:pass@cluster.mongodb.net/email_marketing')}")
        while True:
            uri = input("  MongoDB URI: ").strip()
            if uri.startswith(("mongodb://", "mongodb+srv://")):
                # Quick connectivity test
                info("Testing MongoDB connection...")
                ok_conn, msg = _test_mongo(uri)
                if ok_conn:
                    ok("MongoDB connection successful.")
                    return uri, False
                else:
                    err(f"Connection failed: {msg}")
                    if not _ask_yes_no("Try a different URI?"):
                        fatal("Cannot proceed without a working MongoDB connection.")
            else:
                err("URI must start with mongodb:// or mongodb+srv://")


def ask_redis(features: Dict[str, Any]) -> Tuple[str, bool]:
    """Returns (redis_url, is_local)."""
    step("Redis configuration")
    allows_remote = features.get("remote_redis", False)

    if not allows_remote:
        info("Your plan includes local Redis only.")
        info("A Redis container will be started as part of this installation.")
        return "", True

    print(f"\n  {c(BOLD,'Options:')}")
    print(f"  1. {c(GREEN,'Local')} — run Redis in Docker on this server (recommended)")
    print(f"  2. {c(CYAN,'Remote')} — use an external Redis URL (Upstash, ElastiCache, etc.)")
    choice = _ask_choice("Choose Redis setup", ["1", "2"])

    if choice == "1":
        return "", True
    else:
        print("\n  Enter your Redis URL.")
        print(f"  Example: {c(DIM,'redis://default:password@hostname:6379/0')}")
        while True:
            url = input("  Redis URL: ").strip()
            if url.startswith(("redis://", "rediss://")):
                info("Testing Redis connection...")
                ok_conn, msg = _test_redis(url)
                if ok_conn:
                    ok("Redis connection successful.")
                    return url, False
                else:
                    err(f"Connection failed: {msg}")
                    if not _ask_yes_no("Try a different URL?"):
                        fatal("Cannot proceed without a working Redis connection.")
            else:
                err("URL must start with redis:// or rediss://")


def _test_mongo(uri: str) -> Tuple[bool, str]:
    script = (
        "from pymongo import MongoClient; "
        "c = MongoClient(r'" + uri.replace("'", "\\'") + "', serverSelectionTimeoutMS=5000); "
        "c.admin.command('ping'); print('ok')"
    )
    r = _run([sys.executable, "-c", script], capture=True, check=False)
    if r.returncode == 0 and "ok" in r.stdout:
        return True, ""
    return False, (r.stderr or r.stdout).strip().splitlines()[-1]


def _test_redis(url: str) -> Tuple[bool, str]:
    script = (
        "import redis; "
        "r = redis.Redis.from_url(r'" + url.replace("'", "\\'") + "', socket_timeout=5); "
        "r.ping(); print('ok')"
    )
    r = _run([sys.executable, "-c", script], capture=True, check=False)
    if r.returncode == 0 and "ok" in r.stdout:
        return True, ""
    return False, (r.stderr or r.stdout).strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# Admin user
# ---------------------------------------------------------------------------

def ask_admin_user() -> Dict[str, str]:
    step("Create admin user")
    print("  This account will be used to log in to the dashboard.")
    print("  You can create additional users later via the admin panel.\n")

    name = input("  Admin name: ").strip()
    while not name:
        err("Name cannot be empty.")
        name = input("  Admin name: ").strip()

    while True:
        email = input("  Admin email: ").strip().lower()
        if re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            break
        err("Enter a valid email address.")

    while True:
        pw = getpass("  Admin password (min 8 chars): ")
        if len(pw) < 8:
            err("Password must be at least 8 characters.")
            continue
        pw2 = getpass("  Confirm password: ")
        if pw == pw2:
            break
        err("Passwords do not match. Try again.")

    return {"name": name, "email": email, "password": pw}


# ---------------------------------------------------------------------------
# Secret generation
# ---------------------------------------------------------------------------

def _gen_secret(n: int = 48) -> str:
    return secrets.token_urlsafe(n)


def _gen_mongo_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


# ---------------------------------------------------------------------------
# .env generation
# ---------------------------------------------------------------------------

def generate_env(
    config: Dict[str, Any],
    mongo_password: str,
    install_dir: Path,
) -> None:
    step("Writing backend .env")

    domain     = config["domain"]
    mongo_uri  = config["mongo_uri"]
    redis_url  = config["redis_url"]
    mongo_local = config["mongo_local"]
    redis_local = config["redis_local"]

    if mongo_local:
        mongo_uri = (
            f"mongodb://admin:{mongo_password}@localhost:27017"
            f"/email_marketing?authSource=admin"
        )
        # Inside Docker network we use the service name
        mongo_uri_docker = (
            f"mongodb://admin:{mongo_password}@mongodb:27017"
            f"/email_marketing?authSource=admin"
        )
    else:
        mongo_uri_docker = mongo_uri

    if redis_local:
        redis_url = "redis://redis:6379/0"

    jwt_secret         = _gen_secret(48)
    master_enc_key_raw = secrets.token_bytes(32)
    import base64
    master_enc_key = base64.urlsafe_b64encode(master_enc_key_raw).decode()

    env_content = f"""\
# =========================================================
# ZeniPost Backend Configuration
# Generated by install.py on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
# DO NOT commit this file to version control.
# =========================================================

# ===== APPLICATION =====
ENVIRONMENT=production
DEBUG_MODE=false
LOG_LEVEL=INFO

# ===== DOMAIN =====
APP_DOMAIN={domain}
UNSUBSCRIBE_DOMAIN={domain}
OPEN_TRACKING_DOMAIN={domain}
CLICK_TRACKING_DOMAIN={domain}

# ===== CORS =====
# Populated from APP_DOMAIN automatically in main.py (see CORS section)
ALLOWED_ORIGINS=https://{domain}

# ===== DATABASE =====
MONGODB_URI={mongo_uri_docker}

# ===== REDIS =====
REDIS_URL={redis_url}

# ===== AUTHENTICATION =====
JWT_SECRET={jwt_secret}
JWT_EXP=86400
REFRESH_TOKEN_EXPIRE_DAYS=7

# ===== SECURITY =====
MASTER_ENCRYPTION_KEY={master_enc_key}
PRODUCTION_SAFETY_MODE=true
LOG_SENSITIVE_DATA=false
LOG_EMAIL_CONTENT=false

# ===== REGISTRATION =====
# Self-registration is disabled. Accounts are created via install.py.
# Set to true only if you want open sign-ups.
REGISTRATION_ENABLED=false

# ===== FEATURE FLAGS =====
MOCK_EMAIL_SENDING=false
ENABLE_METRICS_COLLECTION=true
ENABLE_RATE_LIMITING=true
ENABLE_DLQ=true
ENABLE_AUDIT_LOGGING=true
STARTUP_RECOVERY_ENABLED=true

# ===== PERFORMANCE =====
MAX_BATCH_SIZE=1000
MAX_CONCURRENT_TASKS=50
WORKER_MAX_TASKS_PER_CHILD=500
DB_MAX_POOL_SIZE=50
DB_MIN_POOL_SIZE=5

# ===== RATE LIMITING =====
BASE_RATE_LIMIT_PER_MINUTE=100
MAX_RATE_LIMIT_PER_MINUTE=500

# ===== EMAIL PROVIDER =====
# Configure these in the dashboard Settings → Email after first login.
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# SES_CONFIGURATION_SET=
# SMTP_HOST=
# SMTP_PORT=587
# SMTP_USERNAME=
# SMTP_PASSWORD=
# SMTP_USE_TLS=true
"""

    env_path = install_dir / "backend" / ".env"
    env_path.write_text(env_content, encoding="utf-8")
    ok(f"Wrote {env_path}")

    # Store mongo password for docker-compose usage
    config["_mongo_password"]   = mongo_password
    config["_mongo_uri_docker"] = mongo_uri_docker
    config["_redis_url"]        = redis_url


# ---------------------------------------------------------------------------
# docker-compose.yml generation
# ---------------------------------------------------------------------------

DOCKER_COMPOSE_TEMPLATE = """\
# docker-compose.yml — generated by install.py
# Do not edit manually; re-run install.py --reconfigure to regenerate.

version: "3.9"

x-backend-env: &backend-env
  env_file: ./backend/.env
  PYTHONDONTWRITEBYTECODE: "1"
  PYTHONUNBUFFERED: "1"

services:
{mongo_service}
{redis_service}

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: ./backend/.env
    volumes:
      - ./backend:/app
      - uploads:/tmp/uploads
    depends_on:
{backend_depends}
    networks:
      - internal
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

  celery:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: celery -A celery_app worker --loglevel=info --concurrency=4 -Q default,campaigns,analytics
    env_file: ./backend/.env
    volumes:
      - ./backend:/app
      - uploads:/tmp/uploads
    depends_on:
{celery_depends}
    networks:
      - internal

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: celery -A celery_app beat --loglevel=info --scheduler celery.beat:PersistentScheduler
    env_file: ./backend/.env
    volumes:
      - ./backend:/app
      - celery-beat-data:/var/run/celery
    depends_on:
{celery_depends}
    networks:
      - internal

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        VITE_API_BASE_URL: /api
    restart: unless-stopped
    networks:
      - internal

  nginx:
    image: nginx:1.25-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - certbot-webroot:/var/www/certbot:ro
    depends_on:
      - backend
      - frontend
    networks:
      - internal

networks:
  internal:
    driver: bridge

volumes:
  uploads:
  celery-beat-data:
  certbot-webroot:
{extra_volumes}
"""

MONGO_SERVICE = """\
  mongodb:
    image: mongo:7.0
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: {mongo_password}
      MONGO_INITDB_DATABASE: email_marketing
    volumes:
      - mongo-data:/data/db
    networks:
      - internal
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
"""

REDIS_SERVICE = """\
  redis:
    image: redis:7.2-alpine
    restart: unless-stopped
    command: redis-server --save 60 1 --loglevel warning --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - internal
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 15s
      timeout: 5s
      retries: 5
"""


def generate_docker_compose(config: Dict[str, Any], install_dir: Path) -> None:
    step("Writing docker-compose.yml")

    mongo_local = config["mongo_local"]
    redis_local = config["redis_local"]
    mongo_password = config.get("_mongo_password", "")

    mongo_svc   = MONGO_SERVICE.format(mongo_password=mongo_password) if mongo_local else ""
    redis_svc   = REDIS_SERVICE if redis_local else ""

    deps_for_backend = []
    if mongo_local:
        deps_for_backend.append("      - mongodb")
    if redis_local:
        deps_for_backend.append("      - redis")
    if not deps_for_backend:
        deps_for_backend.append("      - frontend")   # at least one dep

    extra_vols = ""
    if mongo_local:
        extra_vols += "  mongo-data:\n"
    if redis_local:
        extra_vols += "  redis-data:\n"

    backend_depends = "\n".join(deps_for_backend)
    celery_depends  = "\n".join(deps_for_backend)  # same

    content = DOCKER_COMPOSE_TEMPLATE.format(
        mongo_service    = mongo_svc.rstrip(),
        redis_service    = redis_svc.rstrip(),
        backend_depends  = backend_depends,
        celery_depends   = celery_depends,
        extra_volumes    = extra_vols,
    )

    (install_dir / "docker-compose.yml").write_text(content, encoding="utf-8")
    ok(f"Wrote {install_dir / 'docker-compose.yml'}")


# ---------------------------------------------------------------------------
# Nginx config generation
# ---------------------------------------------------------------------------

NGINX_HTTP_ONLY = """\
# nginx/nginx.conf — HTTP-only (pre-SSL / Let's Encrypt challenge)
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {{
        root /var/www/certbot;
    }}

    # Temporary: serve app over HTTP until cert is issued
    location /api/ {{
        proxy_pass         http://backend:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }}

    location / {{
        proxy_pass         http://frontend:80;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }}
}}
"""

NGINX_HTTPS = """\
# nginx/nginx.conf — HTTPS with Let's Encrypt
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {{
        root /var/www/certbot;
    }}

    # Redirect all other HTTP → HTTPS
    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {domain};

    ssl_certificate     /etc/nginx/ssl/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/live/{domain}/privkey.pem;

    # Modern TLS
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;

    # HSTS (6 months)
    add_header Strict-Transport-Security "max-age=15768000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-XSS-Protection "1; mode=block";

    client_max_body_size 100M;

    # Backend API
    location /api/ {{
        proxy_pass         http://backend:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_read_timeout 120s;
        proxy_buffering    off;
    }}

    # Tracking / webhook public endpoints (no auth)
    location ~ ^/(track|webhook|unsubscribe|subscribe)/ {{
        proxy_pass         http://backend:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
    }}

    # Frontend
    location / {{
        proxy_pass         http://frontend:80;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        # SPA fallback
        proxy_intercept_errors on;
        error_page 404 = @frontend_fallback;
    }}

    location @frontend_fallback {{
        proxy_pass http://frontend:80/;
    }}
}}
"""


def generate_nginx(domain: str, install_dir: Path, ssl: bool = False) -> None:
    nginx_dir = install_dir / "nginx"
    nginx_dir.mkdir(exist_ok=True)
    (nginx_dir / "ssl").mkdir(exist_ok=True)

    template = NGINX_HTTPS if ssl else NGINX_HTTP_ONLY
    conf = template.format(domain=domain)
    (nginx_dir / "nginx.conf").write_text(conf, encoding="utf-8")
    ok(f"Wrote {nginx_dir / 'nginx.conf'}  ({'HTTPS' if ssl else 'HTTP-only, pre-SSL'})")


# ---------------------------------------------------------------------------
# Let's Encrypt
# ---------------------------------------------------------------------------

def setup_letsencrypt(domain: str, email: str, install_dir: Path) -> bool:
    step(f"Obtaining Let's Encrypt certificate for {domain}")

    ssl_dir = install_dir / "nginx" / "ssl"
    cert_path = ssl_dir / "live" / domain / "fullchain.pem"

    if cert_path.exists():
        ok(f"Certificate already exists at {cert_path}")
        return True

    info("Using certbot Docker image to obtain certificate (standalone mode)...")
    info("Make sure ports 80/443 are open and DNS is pointing here.")

    # Use HTTP challenge via the webroot that nginx mounts
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{ssl_dir}:/etc/letsencrypt",
        "-v", f"{install_dir / 'nginx' / 'certbot-webroot'}:/var/www/certbot",
        # Port 80 must be free OR nginx must already be running with the ACME location
        # We stop nginx first, run standalone, then restart.
        "certbot/certbot",
        "certonly",
        "--standalone",
        "--agree-tos",
        "--no-eff-email",
        "-m", email,
        "-d", domain,
        "--cert-path", f"/etc/letsencrypt/live/{domain}/cert.pem",
        "--key-path",  f"/etc/letsencrypt/live/{domain}/privkey.pem",
        "--fullchain-path", f"/etc/letsencrypt/live/{domain}/fullchain.pem",
        "--chain-path", f"/etc/letsencrypt/live/{domain}/chain.pem",
    ]

    # Temporarily stop nginx so port 80 is free for standalone
    _run(["docker", "compose", "stop", "nginx"], cwd=install_dir, check=False)

    r = _run(cmd, cwd=install_dir, check=False)
    if r.returncode != 0:
        err("certbot failed. Check the output above for details.")
        err("Common causes: DNS not propagated, port 80 not open.")
        warn("The app will start on HTTP only. Re-run 'python3 install.py --reconfigure' after fixing DNS.")
        _run(["docker", "compose", "start", "nginx"], cwd=install_dir, check=False)
        return False

    ok(f"Certificate obtained for {domain}")

    # Write renewal cron
    _setup_cert_renewal(domain, ssl_dir, install_dir)
    return True


def _setup_cert_renewal(domain: str, ssl_dir: Path, install_dir: Path) -> None:
    renew_script = install_dir / "renew-cert.sh"
    script = textwrap.dedent(f"""\
        #!/bin/bash
        # Auto-generated by install.py — runs via cron every 12 hours
        cd {install_dir}
        docker compose stop nginx
        docker run --rm \\
          -v {ssl_dir}:/etc/letsencrypt \\
          certbot/certbot renew --standalone --quiet
        docker compose start nginx
    """)
    renew_script.write_text(script, encoding="utf-8")
    renew_script.chmod(0o755)

    # Add to crontab if not already there
    cron_line = f"0 */12 * * * {renew_script} >> /var/log/cert-renew.log 2>&1"
    r = _run(["crontab", "-l"], capture=True, check=False)
    existing = r.stdout if r.returncode == 0 else ""
    if str(renew_script) not in existing:
        new_cron = (existing.rstrip() + "\n" + cron_line + "\n").lstrip()
        proc = subprocess.run(["crontab", "-"], input=new_cron.encode(), check=False)
        if proc.returncode == 0:
            ok("Added certificate renewal cron job (every 12 hours)")
        else:
            warn(f"Could not add cron job automatically. Add manually:\n  {cron_line}")
    else:
        ok("Certificate renewal cron already present")


# ---------------------------------------------------------------------------
# Docker Compose operations
# ---------------------------------------------------------------------------

def build_and_start(install_dir: Path) -> None:
    step("Building and starting services")

    info("Building Docker images (this may take a few minutes)...")
    _run(["docker", "compose", "build", "--no-cache"], cwd=install_dir)

    info("Starting services...")
    _run(["docker", "compose", "up", "-d"], cwd=install_dir)

    # Wait for backend to be ready
    info("Waiting for backend to become healthy...")
    _wait_for_backend()


def _wait_for_backend(max_wait: int = 90) -> None:
    url = "http://localhost:8000/health"
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    ok("Backend is up and healthy.")
                    return
        except Exception:
            pass
        time.sleep(3)
        print(".", end="", flush=True)
    print()
    warn("Backend did not respond within the timeout. Check logs: docker compose logs backend")


# ---------------------------------------------------------------------------
# Admin user creation via backend API
# ---------------------------------------------------------------------------

def create_admin_user(admin: Dict[str, str], domain: str, use_ssl: bool) -> None:
    step("Creating admin user")

    scheme = "https" if use_ssl else "http"
    base   = f"{scheme}://{domain}"

    # Try via localhost first (avoids DNS dependency)
    for url_base in (f"http://localhost:8000", base):
        try:
            payload = json.dumps({
                "name": admin["name"],
                "email": admin["email"],
                "password": admin["password"],
            }).encode()
            req = urllib.request.Request(
                f"{url_base}/api/auth/register",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    # Pass the setup token so the gated endpoint allows this one call
                    "X-Setup-Token": os.environ.get("SETUP_TOKEN", ""),
                },
                method="POST",
            )
            # Temporarily enable registration for this single call via env trick
            # (The backend checks REGISTRATION_ENABLED; install.py sets it true
            #  only for the duration of this request by restarting with override)
            break
        except Exception:
            pass

    # Re-start backend with REGISTRATION_ENABLED=true for exactly one admin creation
    info("Temporarily enabling registration to create the admin account...")
    _set_env_var(Path("backend/.env"), "REGISTRATION_ENABLED", "true")
    _run(["docker", "compose", "restart", "backend"], cwd=Path("."), check=False)
    _wait_for_backend(60)

    try:
        payload = json.dumps({
            "name": admin["name"],
            "email": admin["email"],
            "password": admin["password"],
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8000/api/auth/register",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            ok(f"Admin account created: {admin['email']}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if "already exists" in body:
            ok(f"Admin account {admin['email']} already exists — skipping creation.")
        else:
            err(f"Failed to create admin user: {exc.code} — {body}")
    except Exception as exc:
        err(f"Failed to create admin user: {exc}")
        warn("You can create the admin user manually later by re-running: python3 install.py --create-user")
    finally:
        # Always lock registration back down
        _set_env_var(Path("backend/.env"), "REGISTRATION_ENABLED", "false")
        _run(["docker", "compose", "restart", "backend"], cwd=Path("."), check=False)
        info("Registration disabled again.")


def _set_env_var(env_path: Path, key: str, value: str) -> None:
    """Update or append a single key=value line in an .env file."""
    if not env_path.exists():
        env_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    lines = env_path.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _run(
    cmd: List[str],
    cwd: Optional[Path] = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    kwargs: Dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "check": False,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"]   = True
    r = subprocess.run(cmd, **kwargs)
    if check and r.returncode != 0:
        fatal(f"Command failed ({r.returncode}): {' '.join(cmd)}")
    return r


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        ans = input(f"{prompt} {hint} ").strip().lower()
        if ans in ("", "y", "yes"):
            return default if ans == "" else True
        if ans in ("n", "no"):
            return False
        err("Please answer y or n.")


def _ask_choice(prompt: str, choices: List[str]) -> str:
    while True:
        ans = input(f"  {prompt} ({'/'.join(choices)}): ").strip()
        if ans in choices:
            return ans
        err(f"Enter one of: {', '.join(choices)}")


def fatal(msg: str) -> None:
    print(f"\n{c(RED+BOLD,'ERROR:')} {msg}\n")
    sys.exit(1)


# ---------------------------------------------------------------------------
# CORS update in backend main.py
# ---------------------------------------------------------------------------

def update_cors(domain: str, install_dir: Path) -> None:
    """
    Patch backend/main.py so CORS allow_origins reads from the ALLOWED_ORIGINS
    environment variable rather than the hardcoded ["*"].
    """
    main_py = install_dir / "backend" / "main.py"
    if not main_py.exists():
        warn("backend/main.py not found — CORS not updated.")
        return

    text = main_py.read_text(encoding="utf-8")

    # Replace the CORSMiddleware block's allow_origins wildcard
    old_pattern = r'allow_origins=\["?\*"?\]'
    new_origins = (
        'allow_origins=(\n'
        '        [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]\n'
        '        or ["*"]\n'
        '    )'
    )

    import re as _re
    if _re.search(old_pattern, text):
        text = _re.sub(old_pattern, new_origins, text)
        # Ensure os is imported (it usually is already)
        if "import os" not in text:
            text = "import os\n" + text
        main_py.write_text(text, encoding="utf-8")
        ok("Updated CORS in backend/main.py to use ALLOWED_ORIGINS env var")
    else:
        warn("Could not auto-patch CORS in main.py — the allow_origins pattern was not found.")
        warn(f"Set ALLOWED_ORIGINS=https://{domain} in backend/.env manually.")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(config: Dict[str, Any], ssl: bool) -> None:
    domain = config["domain"]
    scheme = "https" if ssl else "http"
    url    = f"{scheme}://{domain}"

    print(f"""
{c(GREEN+BOLD,'═'*60)}
{c(GREEN+BOLD,'  ✔  Installation complete!')}
{c(GREEN+BOLD,'═'*60)}

  {c(BOLD,'Access your dashboard:')}  {c(CYAN+BOLD, url)}
  {c(BOLD,'Admin email:')}            {config.get('admin_email', '—')}

  {c(BOLD,'Useful commands:')}
    View logs:        docker compose logs -f
    Restart:          docker compose restart
    Stop:             docker compose down
    Rebuild:          docker compose up -d --build
    Reconfigure:      python3 install.py --reconfigure
    Add user:         python3 install.py --create-user

  {c(BOLD,'Next steps:')}
    1. Log in at {url}
    2. Go to Settings → Email to configure your SMTP or AWS SES provider
    3. Add your first subscriber list and create a campaign
{c(DIM, '  Docs: https://docs.zenipost.com')}
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ZeniPost Email Marketing Platform — Setup Wizard"
    )
    parser.add_argument(
        "--license", metavar="PATH",
        help="Path to license.json (default: auto-detect)",
    )
    parser.add_argument(
        "--reconfigure", action="store_true",
        help="Re-run configuration steps only (skip full install)",
    )
    parser.add_argument(
        "--create-user", action="store_true",
        help="Create an additional admin user and exit",
    )
    parser.add_argument(
        "--skip-ssl", action="store_true",
        help="Skip Let's Encrypt setup (useful for testing on HTTP)",
    )
    args = parser.parse_args()

    banner()

    install_dir = Path(__file__).resolve().parent

    # ── License ──────────────────────────────────────────────────────────────
    license_path = Path(args.license) if args.license else install_dir / "license.json"
    step("Loading license")
    license_data = load_license(license_path)
    features     = validate_license(license_data)
    show_plan_summary(license_data, features)
    print()
    input(f"  {c(DIM,'Press Enter to continue...')}")

    # ── Create-user only mode ─────────────────────────────────────────────
    if args.create_user:
        admin = ask_admin_user()
        config = {
            "domain": license_data.get("domain", "localhost"),
            "admin_email": admin["email"],
        }
        create_admin_user(admin, config["domain"], use_ssl=not args.skip_ssl)
        ok("Done.")
        return

    # ── System requirements ───────────────────────────────────────────────
    check_requirements()

    # ── Domain ───────────────────────────────────────────────────────────
    domain = ask_domain(license_data)

    # ── DNS check ────────────────────────────────────────────────────────
    dns_ok = check_dns(domain)
    if not dns_ok:
        fatal("DNS check failed and user chose not to continue.")

    # ── Database ─────────────────────────────────────────────────────────
    mongo_uri, mongo_local = ask_mongodb(features)
    redis_url, redis_local = ask_redis(features)

    # ── Admin user ───────────────────────────────────────────────────────
    admin = ask_admin_user()

    # ── Confirmation ─────────────────────────────────────────────────────
    mongo_desc = "Local Docker" if mongo_local else (mongo_uri[:40] + "…")
    redis_desc = "Local Docker" if redis_local else (redis_url[:40] + "…")
    ssl_desc   = "Will attempt Let's Encrypt" if not args.skip_ssl else "Skipped"
    print(f"""
{c(BOLD,'  ─── Setup Summary ───')}
  Domain:          {c(GREEN, domain)}
  MongoDB:         {mongo_desc}
  Redis:           {redis_desc}
  Admin email:     {admin['email']}
  SSL:             {ssl_desc}
""")
    if not _ask_yes_no("  Proceed with installation?"):
        fatal("Installation cancelled.")

    # ── Generate secrets and configs ─────────────────────────────────────
    config: Dict[str, Any] = {
        "domain":      domain,
        "mongo_uri":   mongo_uri,
        "mongo_local": mongo_local,
        "redis_url":   redis_url,
        "redis_local": redis_local,
        "admin_email": admin["email"],
    }

    mongo_password = _gen_mongo_password()
    generate_env(config, mongo_password, install_dir)
    generate_docker_compose(config, install_dir)

    # ── CORS ─────────────────────────────────────────────────────────────
    update_cors(domain, install_dir)

    # ── Frontend Dockerfile check ─────────────────────────────────────────
    frontend_dockerfile = install_dir / "frontend" / "Dockerfile"
    if not frontend_dockerfile.exists():
        warn("frontend/Dockerfile not found — frontend container won't build.")
        warn("Make sure you have run: python3 install.py from the repo root.")

    # ── Build & start (HTTP-only first) ───────────────────────────────────
    generate_nginx(domain, install_dir, ssl=False)
    build_and_start(install_dir)

    # ── Let's Encrypt ────────────────────────────────────────────────────
    ssl_ok = False
    if not args.skip_ssl:
        ssl_ok = setup_letsencrypt(domain, admin["email"], install_dir)
        if ssl_ok:
            # Swap nginx config to HTTPS
            generate_nginx(domain, install_dir, ssl=True)
            _run(["docker", "compose", "restart", "nginx"], cwd=install_dir, check=False)
            ok("Nginx reloaded with HTTPS config")
    else:
        warn("SSL skipped. The platform is running on HTTP only.")

    # ── Create admin user ────────────────────────────────────────────────
    create_admin_user(admin, domain, use_ssl=ssl_ok)

    # ── Done ─────────────────────────────────────────────────────────────
    print_summary(config, ssl=ssl_ok)


if __name__ == "__main__":
    main()
