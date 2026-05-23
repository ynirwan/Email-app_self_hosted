#!/usr/bin/env python3
"""
ZeniPost — Browser-Based Setup Wizard (EC2-Native)
====================================================
A WordPress-style installer that runs in the browser.
No pip dependencies required — uses Python stdlib only.

Designed for AWS EC2 AMI deployment:
  • Starts automatically via systemd on instance boot
  • Detects EC2 public IP via instance metadata service
  • Runs a pre-flight check (Docker, disk, security groups)
  • Self-stops after installation completes (no port conflict with nginx)

Usage:
    python3 setup_server.py          # port 8080
    python3 setup_server.py --port 8080 --host 0.0.0.0

Open  http://<EC2-PUBLIC-IP>:8080  in your browser.
(Make sure port 8080 is open in the EC2 Security Group during setup.)
"""

from __future__ import annotations

import argparse
import base64
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
import threading
import time
import traceback
import urllib.request
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("setup")

INSTALL_DIR  = Path(__file__).resolve().parent
SETUP_LOCK   = INSTALL_DIR / ".setup_complete"
SESSION_FILE = INSTALL_DIR / ".setup_session.json"

# Global session state (in-memory, persisted to SESSION_FILE)
_session: Dict[str, Any] = {}
_session_lock = threading.Lock()
# SSE queue for live progress
_progress_queue: Queue = Queue()
# Graceful shutdown — set by run_install() when done so the wizard stops
# itself before docker-compose nginx tries to bind port 80/443.
_shutdown_event = threading.Event()
_server_ref: Optional[HTTPServer] = None   # set in main()
_SETUP_PORT: int = 8080                    # updated in main()

# ---------------------------------------------------------------------------
# Plan feature definitions (mirrors license.py)
# ---------------------------------------------------------------------------
PLAN_FEATURES: Dict[str, Dict[str, Any]] = {
    "starter": {
        "ab_testing": False, "automation": False,
        "deliverability_dashboard": False, "segmentation": True,
        "custom_smtp": True, "api_access": False, "audit_trail": True,
        "remote_db": False, "remote_redis": False,
        "max_users": 1, "max_subscribers": 25_000, "max_campaigns_per_month": -1,
    },
    "professional": {
        "ab_testing": True, "automation": True,
        "deliverability_dashboard": True, "segmentation": True,
        "custom_smtp": True, "api_access": True, "audit_trail": True,
        "remote_db": True, "remote_redis": True,
        "max_users": 1, "max_subscribers": 100_000, "max_campaigns_per_month": -1,
    },
    "enterprise": {
        "ab_testing": True, "automation": True,
        "deliverability_dashboard": True, "segmentation": True,
        "custom_smtp": True, "api_access": True, "audit_trail": True,
        "remote_db": True, "remote_redis": True,
        "max_users": -1, "max_subscribers": -1, "max_campaigns_per_month": -1,
    },
}

_PLAN_ALIASES: Dict[str, str] = {
    "starter":      "starter",
    "pro":          "professional",
    "professional": "professional",
    "agency":       "enterprise",
    "enterprise":   "enterprise",
}

_V2_FLAG_MAP: Dict[str, str] = {
    "ab_testing":            "ab_testing",
    "automation":            "automation",
    "api_access":            "api_access",
    "audit_logs":            "audit_trail",
    "segmentation_advanced": "segmentation",
    "analytics_advanced":    "deliverability_dashboard",
    "team_roles":            "multi_user",
}


def _normalize_plan(plan: str) -> str:
    return _PLAN_ALIASES.get(plan.strip().lower(), "starter")


def _merge_features(plan: str, override: Any) -> dict:
    base = dict(PLAN_FEATURES.get(plan, PLAN_FEATURES["starter"]))
    if isinstance(override, list):
        for flag in override:
            internal = _V2_FLAG_MAP.get(flag)
            if internal and internal in base and isinstance(base[internal], bool):
                base[internal] = True
    elif isinstance(override, dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], bool):
                base[k] = base[k] and bool(v)
            else:
                base[k] = v
    return base


# ---------------------------------------------------------------------------
# Minimal stdlib-only JWT HS256 decoder
# ---------------------------------------------------------------------------

def _decode_jwt_hs256(token: str, secret: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        def _b64_decode(s: str) -> bytes:
            s += "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s)

        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig  = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        actual_sig    = _b64_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(_b64_decode(payload_b64).decode())
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def session_get(key: str, default: Any = None) -> Any:
    with _session_lock:
        return _session.get(key, default)

def session_set(**kwargs: Any) -> None:
    with _session_lock:
        _session.update(kwargs)
    _save_session()

def _save_session() -> None:
    try:
        SESSION_FILE.write_text(json.dumps(_session, default=str), encoding="utf-8")
    except Exception:
        pass

def _load_session() -> None:
    global _session
    if SESSION_FILE.exists():
        try:
            _session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            _session = {}


# ---------------------------------------------------------------------------
# Helper: run subprocess
# ---------------------------------------------------------------------------

def _run(cmd: List[str], cwd: Optional[Path] = None,
         capture: bool = False) -> subprocess.CompletedProcess:
    kwargs: Dict[str, Any] = {"cwd": str(cwd or INSTALL_DIR), "check": False}
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(cmd, **kwargs)


def _push(msg: str, level: str = "info") -> None:
    """Push a progress line to the SSE queue."""
    _progress_queue.put({"msg": msg, "level": level})
    log.info("[progress] %s", msg)


# ---------------------------------------------------------------------------
# License validation
# ---------------------------------------------------------------------------

def validate_license(data: dict) -> Tuple[bool, str, dict]:
    sig    = data.get("signature", "")
    fmt    = data.get("format", "")
    is_v2  = (fmt == "zenipost-license-v2")
    secret = os.getenv("LICENSE_SIGNING_SECRET", "zenipost-license-secret-2026")

    dev_placeholder = sig in ("", "REPLACE_WITH_JWT_FROM_DASHBOARD",
                               "REPLACE_WITH_ACTUAL_SIGNATURE_FROM_VENDOR")

    if not dev_placeholder:
        if is_v2:
            payload = _decode_jwt_hs256(sig, secret)
            if payload is None:
                return False, "License signature verification failed. The file may have been tampered with or the LICENSE_SIGNING_SECRET is wrong.", {}
            for check_key in ("license_id", "domain", "plan", "expires_at"):
                plain_val = data.get(check_key)
                jwt_val   = payload.get(check_key)
                if plain_val is not None and jwt_val is not None and plain_val != jwt_val:
                    return False, f"License tamper detected: '{check_key}' mismatch between file and signature.", {}
        else:
            canonical = json.dumps(
                {k: v for k, v in data.items() if k not in ("signature", "_comment")},
                sort_keys=True, separators=(",", ":"),
            ).encode()
            expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig.lower()):
                return False, "License signature verification failed. The file may have been tampered with.", {}

    expires_raw = data.get("expires_at", "9999-12-31")
    try:
        expires = date.fromisoformat(expires_raw[:10])
    except (ValueError, TypeError):
        return False, f"Invalid expires_at date: {expires_raw}", {}
    if date.today() > expires:
        return False, f"License expired on {expires}. Please renew.", {}

    raw_plan = data.get("plan", "starter")
    plan = _normalize_plan(raw_plan)
    if plan not in PLAN_FEATURES:
        return False, f"Unknown plan '{raw_plan}'.", {}

    if not data.get("domain", "").strip():
        return False, "License has no 'domain' field.", {}

    features = _merge_features(plan, data.get("features", []))
    return True, "", features


# ---------------------------------------------------------------------------
# License file writer — keeps root + backend/ in sync
# ---------------------------------------------------------------------------

def _write_license(data: dict) -> None:
    """
    Write license.json to both required locations:

      • INSTALL_DIR/license.json         — used by _register_install() and wizard
      • INSTALL_DIR/backend/license.json — mounted into the container as
                                           /app/license.json  (volume: ./backend:/app)

    main.py looks for the file at /app/license.json on startup. If the backend
    copy is absent the app refuses to start with RuntimeError.
    """
    payload = json.dumps(data, indent=2)
    (INSTALL_DIR / "license.json").write_text(payload, encoding="utf-8")
    backend_dir = INSTALL_DIR / "backend"
    backend_dir.mkdir(exist_ok=True)
    (backend_dir / "license.json").write_text(payload, encoding="utf-8")


# ---------------------------------------------------------------------------
# DNS check
# ---------------------------------------------------------------------------

def check_dns_record(domain: str) -> Tuple[bool, str, str]:
    server_ip = _get_public_ip() or ""
    try:
        resolved_ip = socket.gethostbyname(domain)
    except socket.gaierror:
        return False, server_ip, ""
    return (resolved_ip == server_ip and bool(server_ip)), server_ip, resolved_ip


def _get_ec2_public_ip() -> Optional[str]:
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(token_req, timeout=2) as r:
            token = r.read().decode().strip()
        ip_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/public-ipv4",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(ip_req, timeout=2) as r:
            ip = r.read().decode().strip()
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                return ip
    except Exception:
        pass
    try:
        with urllib.request.urlopen(
            "http://169.254.169.254/latest/meta-data/public-ipv4", timeout=2
        ) as r:
            ip = r.read().decode().strip()
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                return ip
    except Exception:
        pass
    return None


def _get_ec2_instance_id() -> Optional[str]:
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(token_req, timeout=2) as r:
            token = r.read().decode().strip()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def _get_ec2_region() -> Optional[str]:
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(token_req, timeout=2) as r:
            token = r.read().decode().strip()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/placement/region",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def _get_public_ip() -> Optional[str]:
    ec2_ip = _get_ec2_public_ip()
    if ec2_ip:
        return ec2_ip
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                ip = r.read().decode().strip()
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                    return ip
        except Exception:
            pass
    return None


def _is_ip_address(s: str) -> bool:
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", s.strip()))


def run_preflight() -> Dict[str, Any]:
    checks = []

    # ── Docker ────────────────────────────────────────────────────────────────
    r = _run(["docker", "--version"], capture=True)
    docker_ok = r.returncode == 0
    checks.append({
        "name": "Docker installed",
        "ok": docker_ok,
        "detail": r.stdout.strip().split("\n")[0] if docker_ok else "Docker not found — install from https://docs.docker.com/get-docker/",
    })

    # ── Docker daemon ─────────────────────────────────────────────────────────
    if docker_ok:
        r2 = _run(["docker", "info"], capture=True)
        daemon_ok = r2.returncode == 0
        checks.append({
            "name": "Docker daemon running",
            "ok": daemon_ok,
            "detail": "Running" if daemon_ok else "Docker daemon not running — try: sudo systemctl start docker",
        })
    else:
        daemon_ok = False

    # ── Docker Compose v2 ─────────────────────────────────────────────────────
    r3 = _run(["docker", "compose", "version"], capture=True)
    compose_ok = r3.returncode == 0
    checks.append({
        "name": "Docker Compose v2",
        "ok": compose_ok,
        "detail": r3.stdout.strip() if compose_ok else "Not found — install docker-compose-plugin",
    })

    # ── Disk space ────────────────────────────────────────────────────────────
    try:
        stat = shutil.disk_usage(str(INSTALL_DIR))
        free_gb = stat.free / (1024 ** 3)
        disk_ok = free_gb >= 5
        checks.append({
            "name": "Disk space (≥5 GB free)",
            "ok": disk_ok,
            "detail": f"{free_gb:.1f} GB free",
        })
    except Exception as exc:
        checks.append({"name": "Disk space", "ok": False, "detail": str(exc)})

    # ── Python version ────────────────────────────────────────────────────────
    py_ok = sys.version_info >= (3, 8)
    checks.append({
        "name": "Python 3.8+",
        "ok": py_ok,
        "detail": sys.version.split()[0],
    })

    # ── Dockerfiles present ───────────────────────────────────────────────────
    for svc, rel in [("backend", "backend/Dockerfile"), ("frontend", "frontend/Dockerfile")]:
        df_path = INSTALL_DIR / rel
        df_ok = df_path.exists() and df_path.stat().st_size > 10
        checks.append({
            "name": f"Dockerfile present ({svc})",
            "ok":   df_ok,
            "detail": str(df_path) if df_ok else (
                f"Missing or empty: {df_path} — re-deploy application files or re-bake AMI"
            ),
        })

    # ── EC2 public IP ─────────────────────────────────────────────────────────
    public_ip   = _get_public_ip()
    instance_id = _get_ec2_instance_id()
    region      = _get_ec2_region()

    checks.append({
        "name": "Public IP detected",
        "ok": bool(public_ip),
        "detail": public_ip or "Could not detect — may not be EC2 or metadata is blocked",
    })

    all_ok = all(c["ok"] for c in checks)
    return {
        "ok": all_ok,
        "checks": checks,
        "public_ip": public_ip or "",
        "instance_id": instance_id or "",
        "region": region or "",
        "setup_port": _SETUP_PORT,
    }


# ---------------------------------------------------------------------------
# Connectivity tests
# ---------------------------------------------------------------------------

def test_mongo(uri: str) -> Tuple[bool, str]:
    script = (
        "from pymongo import MongoClient; "
        f"c = MongoClient(r'{uri}', serverSelectionTimeoutMS=5000); "
        "c.admin.command('ping'); print('ok')"
    )
    r = _run([sys.executable, "-c", script], capture=True)
    if r.returncode == 0 and "ok" in r.stdout:
        return True, ""
    lines = (r.stderr or r.stdout or "Unknown error").strip().splitlines()
    return False, lines[-1]


def test_redis(url: str) -> Tuple[bool, str]:
    script = (
        "import redis; "
        f"r = redis.Redis.from_url(r'{url}', socket_timeout=5); "
        "r.ping(); print('ok')"
    )
    r = _run([sys.executable, "-c", script], capture=True)
    if r.returncode == 0 and "ok" in r.stdout:
        return True, ""
    lines = (r.stderr or r.stdout or "Unknown error").strip().splitlines()
    return False, lines[-1]


# ---------------------------------------------------------------------------
# Config generation helpers
# ---------------------------------------------------------------------------

def _gen_secret(n: int = 48) -> str:
    return secrets.token_urlsafe(n)

def _gen_mongo_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


def _extract_mongo_password(env_path: Path) -> Optional[str]:
    """
    Read the MongoDB password previously written to backend/.env.

    On a retry after a partial install, the mongo-data volume already exists
    and Docker ignores MONGO_INITDB_* env vars — it uses whatever password the
    volume was initialised with. Reusing the existing password prevents auth
    failures. Returns None if the file doesn't exist or the key isn't present.
    """
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = re.search(r"mongodb://admin:([^@]+)@", line)
        if m:
            pwd = m.group(1)
            if pwd and len(pwd) >= 8:
                return pwd
    return None


def write_env(config: dict) -> None:
    domain         = config["domain"]
    mongo_local    = config["mongo_local"]
    redis_local    = config["redis_local"]
    mongo_password = config["mongo_password"]

    if mongo_local:
        mongo_uri_docker = (
            f"mongodb://admin:{mongo_password}@mongodb:27017"
            "/email_marketing?authSource=admin"
        )
    else:
        mongo_uri_docker = config.get("mongo_uri", "")

    redis_url = "redis://redis:6379/0" if redis_local else config.get("redis_url", "")

    jwt_secret  = _gen_secret(48)
    enc_key_raw = secrets.token_bytes(32)
    enc_key     = base64.urlsafe_b64encode(enc_key_raw).decode()

    _no_ssl = config.get("skip_ssl", False) or _is_ip_address(domain)
    _scheme = "http" if _no_ssl else "https"

    license_signing_secret = os.getenv("LICENSE_SIGNING_SECRET", "zenipost-license-secret-2026")
    admin_access_secret    = os.getenv("ADMIN_ACCESS_SECRET",    "zenipost-admin-access-secret-2026")

    content = f"""\
# ZeniPost Backend Configuration
# Generated by setup_server.py on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
# DO NOT commit this file.

ENVIRONMENT=production
DEBUG_MODE=false
LOG_LEVEL=INFO

APP_DOMAIN={domain}
UNSUBSCRIBE_DOMAIN={domain}
OPEN_TRACKING_DOMAIN={domain}
CLICK_TRACKING_DOMAIN={domain}
ALLOWED_ORIGINS={_scheme}://{domain}

MONGODB_URI={mongo_uri_docker}
REDIS_URL={redis_url}

JWT_SECRET={jwt_secret}
JWT_EXP=86400
REFRESH_TOKEN_EXPIRE_DAYS=7

MASTER_ENCRYPTION_KEY={enc_key}
PRODUCTION_SAFETY_MODE=true
LOG_SENSITIVE_DATA=false
LOG_EMAIL_CONTENT=false

REGISTRATION_ENABLED=false

MOCK_EMAIL_SENDING=false
ENABLE_METRICS_COLLECTION=true
ENABLE_RATE_LIMITING=true
ENABLE_DLQ=true
ENABLE_AUDIT_LOGGING=true
STARTUP_RECOVERY_ENABLED=true

MAX_BATCH_SIZE=1000
MAX_CONCURRENT_TASKS=50
DB_MAX_POOL_SIZE=50
DB_MIN_POOL_SIZE=5
BASE_RATE_LIMIT_PER_MINUTE=100
MAX_RATE_LIMIT_PER_MINUTE=500

# ── ZeniPost License ──────────────────────────────────────────────────────────
LICENSE_SIGNING_SECRET={license_signing_secret}
ADMIN_ACCESS_SECRET={admin_access_secret}
"""
    env_path = INSTALL_DIR / "backend" / ".env"
    env_path.write_text(content, encoding="utf-8")
    config["_redis_url"]        = redis_url
    config["_mongo_uri_docker"] = mongo_uri_docker


def write_docker_compose(config: dict) -> None:
    mongo_local    = config["mongo_local"]
    redis_local    = config["redis_local"]
    mongo_password = config["mongo_password"]

    mongo_svc = f"""
  mongodb:
    image: mongo:7.0
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: {mongo_password}
      MONGO_INITDB_DATABASE: email_marketing
    volumes:
      - mongo-data:/data/db
    networks: [internal]
    healthcheck:
      test: ["CMD","mongosh","--eval","db.adminCommand('ping')"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
""" if mongo_local else ""

    redis_svc = """
  redis:
    image: redis:7.2-alpine
    restart: unless-stopped
    command: redis-server --save 60 1 --loglevel warning --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks: [internal]
    healthcheck:
      test: ["CMD","redis-cli","ping"]
      interval: 15s
      timeout: 5s
      retries: 5
""" if redis_local else ""

    deps = []
    if mongo_local: deps.append("      - mongodb")
    if redis_local: deps.append("      - redis")
    if not deps:    deps.append("      - frontend")
    deps_str = "\n".join(deps)

    extra_vols  = "  mongo-data:\n" if mongo_local else ""
    extra_vols += "  redis-data:\n" if redis_local else ""

    # NOTE: no `version:` key — obsolete in Compose v2, causes warnings
    compose = f"""services:
{mongo_svc}
{redis_svc}
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
{deps_str}
    networks: [internal]
    healthcheck:
      test: ["CMD","curl","-f","http://localhost:8000/health"]
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
{deps_str}
    networks: [internal]

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: celery -A celery_app beat --loglevel=info
    env_file: ./backend/.env
    volumes:
      - ./backend:/app
      - celery-beat-data:/var/run/celery
    depends_on:
{deps_str}
    networks: [internal]

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        VITE_API_BASE_URL: /api
    restart: unless-stopped
    networks: [internal]

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
    depends_on: [backend, frontend]
    networks: [internal]

networks:
  internal:
    driver: bridge

volumes:
  uploads:
  celery-beat-data:
  certbot-webroot:
{extra_vols}"""

    (INSTALL_DIR / "docker-compose.yml").write_text(compose, encoding="utf-8")


def write_nginx(domain: str, ssl: bool = False) -> None:
    nginx_dir = INSTALL_DIR / "nginx"
    nginx_dir.mkdir(exist_ok=True)
    (nginx_dir / "ssl").mkdir(exist_ok=True)

    domain_is_ip = _is_ip_address(domain)
    server_name_directive = (
        f"server_name {domain} _;"
        if domain_is_ip
        else f"server_name {domain};"
    )

    if ssl and not domain_is_ip:
        conf = f"""server {{
    listen 80; listen [::]:80;
    {server_name_directive}
    location /.well-known/acme-challenge/ {{ root /var/www/certbot; }}
    location / {{ return 301 https://$host$request_uri; }}
}}
server {{
    listen 443 ssl http2; listen [::]:443 ssl http2;
    {server_name_directive}
    ssl_certificate     /etc/nginx/ssl/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    add_header Strict-Transport-Security "max-age=15768000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    client_max_body_size 100M;
    location /api/ {{
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }}
    location ~ ^/(track|webhook|unsubscribe|subscribe)/ {{
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }}
    location / {{
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }}
}}"""
    else:
        conf = f"""server {{
    listen 80; listen [::]:80;
    {server_name_directive}
    client_max_body_size 100M;
    location /.well-known/acme-challenge/ {{ root /var/www/certbot; }}
    location /api/ {{
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_buffering off;
    }}
    location ~ ^/(track|webhook|unsubscribe|subscribe)/ {{
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    location / {{
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_intercept_errors on;
        error_page 404 = @frontend_fallback;
    }}
    location @frontend_fallback {{
        proxy_pass http://frontend:80;
    }}
}}"""

    (nginx_dir / "nginx.conf").write_text(conf, encoding="utf-8")


def set_env_var(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    found, new_lines = False, []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}"); found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def update_cors_in_main(domain: str) -> None:
    main_py = INSTALL_DIR / "backend" / "main.py"
    if not main_py.exists():
        return
    text = main_py.read_text(encoding="utf-8")
    new_origins = (
        'allow_origins=(\n'
        '        [o.strip() for o in os.getenv("ALLOWED_ORIGINS","").split(",") if o.strip()]\n'
        '        or ["*"]\n'
        '    )'
    )
    updated = re.sub(r'allow_origins=\["?\*"?\]', new_origins, text)
    if updated != text:
        if "import os" not in updated:
            updated = "import os\n" + updated
        main_py.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Install runner
# ---------------------------------------------------------------------------

def run_install(config: dict) -> None:
    try:
        _push("Starting installation…", "info")

        domain         = config["domain"]
        admin_email    = config["admin_email"]
        admin_name     = config["admin_name"]
        admin_password = config["admin_password"]
        skip_ssl       = config.get("skip_ssl", False)

        if _is_ip_address(domain):
            if not skip_ssl:
                _push(
                    f"Domain is an IP address ({domain}) — SSL/Let's Encrypt requires "
                    "a real domain name. Switching to HTTP-only mode automatically.",
                    "warn",
                )
            skip_ssl = True
            config["skip_ssl"] = True

        # ── Step 0: wipe any previous partial install ─────────────────────────
        # Guarantees MongoDB re-initialises with the password in the new .env.
        # Docker ignores MONGO_INITDB_* on an existing volume, so old containers
        # + volumes must be removed before each install attempt.
        _push("Removing any previous partial install (containers + volumes)…")
        wipe = subprocess.run(
            ["docker", "compose", "down", "--volumes", "--remove-orphans"],
            cwd=str(INSTALL_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in wipe.stdout.splitlines():
            if line.strip():
                _push(f"  {line.strip()}")
        _push("Previous state cleared ✔", "ok")

        # ── Step 1: Write .env ────────────────────────────────────────────────
        _push("Writing backend/.env …")
        write_env(config)
        _push("backend/.env written ✔", "ok")

        # ── Step 1b: Deploy license.json to backend/ ──────────────────────────
        # The backend container mounts ./backend as /app, so it looks for the
        # license at /app/license.json = backend/license.json on the host.
        # main.py raises RuntimeError on startup if this file is missing.
        _push("Deploying license.json to backend/ …")
        lic_data = config.get("license") or {}
        if lic_data:
            _write_license(lic_data)
            _push("license.json deployed ✔", "ok")
        elif (INSTALL_DIR / "license.json").exists():
            raw = (INSTALL_DIR / "license.json").read_text(encoding="utf-8")
            (INSTALL_DIR / "backend" / "license.json").write_text(raw, encoding="utf-8")
            _push("license.json copied to backend/ ✔", "ok")
        else:
            raise RuntimeError(
                "license.json not found. Please complete the License step before installing."
            )

        # ── Step 2: docker-compose.yml ────────────────────────────────────────
        _push("Writing docker-compose.yml …")
        write_docker_compose(config)
        _push("docker-compose.yml written ✔", "ok")

        # ── Step 3: nginx HTTP-only config ────────────────────────────────────
        _push("Writing nginx config (HTTP) …")
        write_nginx(domain, ssl=False)
        _push("nginx config written ✔", "ok")

        # ── Step 4: CORS patch ────────────────────────────────────────────────
        _push("Patching CORS in backend/main.py …")
        update_cors_in_main(domain)
        _push("CORS patched ✔", "ok")

        # ── Step 5: docker compose build ──────────────────────────────────────
        _push("Building Docker images — this may take 3–6 minutes …", "warn")
        r = subprocess.run(
            ["docker", "compose", "build", "--no-cache"],
            cwd=str(INSTALL_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in r.stdout.splitlines():
            if line.strip():
                _push(f"  {line.strip()}")
        if r.returncode != 0:
            raise RuntimeError("docker compose build failed. Check logs above.")
        _push("Docker build complete ✔", "ok")

        # ── Step 6: Start services ────────────────────────────────────────────
        _push("Starting services …")
        r2 = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=str(INSTALL_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in r2.stdout.splitlines():
            if line.strip():
                _push(f"  {line.strip()}")
        if r2.returncode != 0:
            raise RuntimeError("docker compose up failed.")
        _push("All services started ✔", "ok")

        # ── Step 7: Wait for backend health ───────────────────────────────────
        _push("Waiting for backend to become healthy …")
        _wait_for_backend()
        _push("Backend healthy ✔", "ok")

        # ── Step 8: Let's Encrypt ─────────────────────────────────────────────
        ssl_ok = False
        if not skip_ssl:
            _push(f"Requesting Let's Encrypt certificate for {domain} …")
            ssl_ok = _letsencrypt(domain, admin_email)
            if ssl_ok:
                _push("SSL certificate obtained ✔", "ok")
                write_nginx(domain, ssl=True)
                subprocess.run(["docker", "compose", "restart", "nginx"],
                               cwd=str(INSTALL_DIR), check=False)
                _push("nginx reloaded with HTTPS config ✔", "ok")
            else:
                _push("SSL setup failed — running on HTTP. You can retry later.", "warn")
        else:
            _push("SSL skipped (running on HTTP).", "warn")

        # ── Step 9: Create admin user ─────────────────────────────────────────
        _push(f"Creating admin account for {admin_email} …")
        _create_admin(admin_name, admin_email, admin_password)

        # ── Step 10: Register with ZeniPost Dashboard ─────────────────────────
        _register_install(config)

        # ── Step 11: Write setup lock ─────────────────────────────────────────
        scheme  = "https" if ssl_ok else "http"
        app_url = f"{scheme}://{domain}"
        SETUP_LOCK.write_text(
            json.dumps({"completed_at": datetime.utcnow().isoformat(), "url": app_url}),
            encoding="utf-8",
        )
        session_set(install_complete=True, app_url=app_url, ssl=ssl_ok)

        _progress_queue.put({"msg": "DONE", "level": "done", "app_url": app_url})
        log.info("[progress] DONE — app_url=%s", app_url)

        def _delayed_shutdown():
            time.sleep(8)
            _shutdown_event.set()
            if _server_ref:
                threading.Thread(target=_server_ref.shutdown, daemon=True).start()
        threading.Thread(target=_delayed_shutdown, daemon=True).start()

    except Exception as exc:
        _push(f"INSTALL FAILED: {exc}", "error")
        _push(traceback.format_exc(), "error")


def _register_install(config: dict) -> None:
    license_path = INSTALL_DIR / "license.json"
    if not license_path.exists():
        log.warning("register-install: license.json not found, skipping registration")
        return

    try:
        raw = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("register-install: could not read license.json: %s", exc)
        return

    ping_url = raw.get("ping_url", "")
    if not ping_url:
        log.info("register-install: no ping_url in license (dev/legacy mode), skipping")
        return

    register_url = ping_url.rsplit("/ping", 1)[0] + "/register-install"
    signature    = raw.get("signature", "")
    domain       = config.get("domain", raw.get("domain", ""))
    server_ip    = _get_public_ip() or ""

    payload = json.dumps({
        "domain":    domain,
        "signature": signature,
        "server_ip": server_ip,
    }).encode()

    _push(f"Registering installation with ZeniPost Dashboard (IP: {server_ip or 'unknown'}) …")
    try:
        req = urllib.request.Request(
            register_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read().decode())
        if resp.get("ip_changed"):
            _push("⚠ Dashboard flagged this as a re-install on a different IP.", "warn")
        else:
            _push("Installation registered with ZeniPost Dashboard ✔", "ok")
    except Exception as exc:
        log.warning("register-install request failed (non-fatal): %s", exc)
        _push("Could not reach ZeniPost Dashboard for install registration (non-fatal).", "warn")


def _wait_for_backend(max_wait: int = 120) -> None:
    """
    Wait until the backend container responds healthy.

    Uses `docker compose exec` so the health check runs inside the Docker
    network — the backend has no host-side port mapping, so localhost:8000
    is NOT reachable from the host process that runs setup_server.py.
    """
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend",
             "curl", "-sf", "--max-time", "3", "http://localhost:8000/health"],
            cwd=str(INSTALL_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if r.returncode == 0:
            return
        time.sleep(3)
    raise RuntimeError(
        "Backend did not become healthy within the timeout. "
        "Check logs: docker compose logs backend"
    )


def _letsencrypt(domain: str, email: str) -> bool:
    ssl_dir = INSTALL_DIR / "nginx" / "ssl"
    cert = ssl_dir / "live" / domain / "fullchain.pem"
    if cert.exists():
        return True
    subprocess.run(["docker", "compose", "stop", "nginx"],
                   cwd=str(INSTALL_DIR), check=False)
    r = subprocess.run([
        "docker", "run", "--rm",
        "-v", f"{ssl_dir}:/etc/letsencrypt",
        "certbot/certbot", "certonly",
        "--standalone", "--agree-tos", "--no-eff-email",
        "-m", email, "-d", domain,
    ], cwd=str(INSTALL_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in r.stdout.splitlines():
        if line.strip(): _push(f"  certbot: {line.strip()}")
    subprocess.run(["docker", "compose", "start", "nginx"],
                   cwd=str(INSTALL_DIR), check=False)
    return r.returncode == 0


def _create_admin(name: str, email: str, password: str) -> None:
    """
    Create the initial admin user directly in MongoDB from inside
    the backend container.

    This bypasses REGISTRATION_ENABLED completely.
    """

    script = r"""
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

try:
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hash_pw = pwd.hash
except Exception:
    import hashlib
    import secrets

    def hash_pw(pw):
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + pw).encode()).hexdigest()
        return f"sha256${salt}${h}"

uri   = os.environ["MONGODB_URI"]
name  = os.environ["ADMIN_NAME"]
email = os.environ["ADMIN_EMAIL"]
pw    = os.environ["ADMIN_PASSWORD"]

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client.get_default_database()

existing = db.users.find_one({"email": email})

if existing:
    print("exists")
    sys.exit(0)

db.users.insert_one({
    "name": name,
    "email": email,
    "password": hash_pw(pw),
    "role": "admin",
    "is_active": True,
    "is_verified": True,
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
})

print("created")
"""

    r = subprocess.run(
        [
            "docker", "compose", "exec", "-T",

            "-e", f"ADMIN_NAME={name}",
            "-e", f"ADMIN_EMAIL={email}",
            "-e", f"ADMIN_PASSWORD={password}",

            "backend",
            "python3",
            "-c",
            script,
        ],
        cwd=str(INSTALL_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output = (r.stdout or "").strip()
    stderr = (r.stderr or "").strip()

    if r.returncode != 0:
        raise RuntimeError(
            f"Admin creation failed: {output or stderr}"
        )

    if output == "exists":
        _push(f"Admin account {email} already exists — skipping.", "warn")
    elif output == "created":
        _push(f"Admin account {email} created ✔", "ok")
    else:
        _push(f"Admin creation result: {output}", "warn")

# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ZeniPost — Setup Wizard</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background: linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%); min-height:100vh; }
  .card { background: rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); }
  .step-dot { transition: all .3s; }
  .step-dot.active  { background:#6366f1; border-color:#6366f1; color:#fff; }
  .step-dot.done    { background:#10b981; border-color:#10b981; color:#fff; }
  .step-dot.pending { background:transparent; border-color:#4b5563; color:#6b7280; }
  .btn-primary { background:linear-gradient(135deg,#6366f1,#8b5cf6); transition:opacity .2s; }
  .btn-primary:hover { opacity:.9; }
  .btn-primary:disabled { opacity:.4; cursor:not-allowed; }
  .log-line { font-family:monospace; font-size:.8rem; padding:2px 0; }
  .log-ok    { color:#34d399; }
  .log-warn  { color:#fbbf24; }
  .log-error { color:#f87171; }
  .log-info  { color:#94a3b8; }
  .log-done  { color:#6366f1; font-weight:bold; }
  input, textarea {
    background:rgba(255,255,255,0.05) !important;
    border:1px solid rgba(255,255,255,0.1);
    color:#e2e8f0 !important;
    border-radius:0.5rem;
    padding:.6rem .9rem;
    width:100%;
    outline:none;
  }
  input:focus, textarea:focus { border-color:#6366f1; box-shadow:0 0 0 2px rgba(99,102,241,.3); }
  input::placeholder { color:#64748b; }
  select {
    background:rgba(15,23,42,0.8);
    border:1px solid rgba(255,255,255,0.1);
    color:#e2e8f0;
    border-radius:0.5rem;
    padding:.6rem .9rem;
    width:100%;
    outline:none;
  }
  .feature-badge { display:inline-flex; align-items:center; gap:.3rem;
    font-size:.75rem; padding:.2rem .6rem; border-radius:9999px; }
  .badge-green { background:rgba(16,185,129,.15); color:#34d399; }
  .badge-gray  { background:rgba(100,116,139,.15); color:#64748b; }
  .step-panel  { display:none; }
  .step-panel.active { display:block; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .spinner { animation:spin 1s linear infinite; }
</style>
</head>
<body class="flex items-center justify-center px-4 py-12">
<div class="w-full max-w-2xl">

  <div class="text-center mb-8">
    <div class="text-3xl font-black text-white tracking-tight mb-1">
      <span class="text-indigo-400">Zeni</span>Post
    </div>
    <p class="text-slate-400 text-sm">Self-Hosted Setup Wizard</p>
  </div>

  <div class="flex items-center justify-center gap-0 mb-8" id="step-indicators"></div>

  <div class="card rounded-2xl p-8 shadow-2xl">
    <div id="panels">

      <!-- STEP 1: Pre-flight -->
      <div class="step-panel active" id="panel-1">
        <h2 class="text-xl font-bold text-white mb-1">Server pre-flight check</h2>
        <p class="text-slate-400 text-sm mb-5">Verifying your EC2 instance is ready to install ZeniPost.</p>
        <div class="rounded-xl p-4 mb-5 flex flex-wrap gap-4"
          style="background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.18)">
          <div>
            <p class="text-slate-500 text-xs uppercase tracking-wider mb-0.5">Public IP</p>
            <p id="pf-server-ip" class="text-indigo-300 font-mono font-semibold text-sm">detecting…</p>
          </div>
          <div>
            <p class="text-slate-500 text-xs uppercase tracking-wider mb-0.5">Instance ID</p>
            <p id="pf-instance" class="text-slate-300 font-mono text-sm">—</p>
          </div>
          <div>
            <p class="text-slate-500 text-xs uppercase tracking-wider mb-0.5">Region</p>
            <p id="pf-region" class="text-slate-300 font-mono text-sm">—</p>
          </div>
        </div>
        <div class="rounded-xl p-3 mb-5 flex gap-3 items-start"
          style="background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.2)">
          <span class="text-yellow-400 text-lg mt-0.5">⚠</span>
          <div class="text-sm">
            <p class="text-yellow-300 font-semibold mb-1">EC2 Security Group — required ports</p>
            <p class="text-slate-400 mb-1">Open these inbound rules before continuing:</p>
            <div class="font-mono text-xs space-y-0.5 text-slate-300">
              <div>TCP <strong class="text-white">8080</strong> — setup wizard (this page)</div>
              <div>TCP <strong class="text-white">80</strong>   — HTTP / Let's Encrypt challenge</div>
              <div>TCP <strong class="text-white">443</strong>  — HTTPS (after SSL setup)</div>
              <div>TCP <strong class="text-white">22</strong>   — SSH (your IP only)</div>
            </div>
            <p class="text-slate-500 text-xs mt-2">
              After setup completes you can remove port <span id="sg-port">8080</span> from the security group.
            </p>
          </div>
        </div>
        <div id="preflight-list" class="mb-5 divide-y divide-white/5">
          <div class="text-slate-400 text-sm py-3 animate-pulse">Running checks…</div>
        </div>
        <div class="flex justify-between items-center">
          <button onclick="runPreflight()" class="text-sm text-indigo-400 hover:text-indigo-300">↺ Re-run checks</button>
          <button id="pf-next" onclick="goTo(2)" disabled
            class="btn-primary text-white font-semibold rounded-xl px-6 py-2.5 opacity-40">
            Continue →
          </button>
        </div>
      </div>

      <!-- STEP 2: License -->
      <div class="step-panel" id="panel-2">
        <h2 class="text-xl font-bold text-white mb-1">Upload your license</h2>
        <p class="text-slate-400 text-sm mb-6">Paste the contents of your <code class="text-indigo-300">license.json</code> file or upload it.</p>
        <div class="mb-4">
          <label class="text-slate-300 text-sm mb-2 block">license.json</label>
          <textarea id="license-json" rows="10" placeholder='{"license_key":"...","domain":"...","plan":"professional",...}'
            class="font-mono text-xs"></textarea>
        </div>
        <p class="text-slate-500 text-xs mb-4">— or —</p>
        <input type="file" id="license-file" accept=".json" class="text-slate-400 text-sm mb-6"/>
        <div id="license-error" class="hidden text-red-400 text-sm bg-red-900/20 rounded-lg p-3 mb-4"></div>
        <div id="license-summary" class="hidden rounded-xl p-4 mb-4" style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.2)"></div>
        <div class="flex justify-between mt-4">
          <button onclick="goTo(1)" class="text-slate-400 hover:text-white text-sm px-4 py-2">← Back</button>
          <button onclick="validateLicense()" class="btn-primary text-white font-semibold rounded-xl px-6 py-2.5">
            Validate & Continue →
          </button>
        </div>
      </div>

      <!-- STEP 3: Domain -->
      <div class="step-panel" id="panel-3">
        <h2 class="text-xl font-bold text-white mb-1">Domain setup</h2>
        <p class="text-slate-400 text-sm mb-6">Configure which domain the platform will be accessible on.</p>
        <div class="mb-4">
          <label class="text-slate-300 text-sm mb-1 block">Licensed domain</label>
          <input id="licensed-domain" readonly class="opacity-60"/>
        </div>
        <div class="mb-4">
          <label class="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
            <input type="checkbox" id="use-subdomain" class="w-auto" onchange="toggleSubdomain()"/>
            Run on a subdomain (e.g. <span id="sub-example" class="text-indigo-300">app.yourdomain.com</span>)
          </label>
        </div>
        <div id="subdomain-row" class="mb-4 hidden">
          <label class="text-slate-300 text-sm mb-1 block">Subdomain prefix</label>
          <div class="flex gap-2 items-center">
            <input id="subdomain-prefix" placeholder="app" class="w-32" oninput="updateSubdomainPreview()"/>
            <span class="text-slate-400">.</span>
            <span id="sub-domain-suffix" class="text-slate-300 font-mono"></span>
          </div>
        </div>
        <div class="mb-4 p-3 rounded-xl" style="background:rgba(15,23,42,.6);border:1px solid rgba(255,255,255,.07)">
          <p class="text-slate-300 text-sm">Final domain: <strong id="final-domain" class="text-indigo-300"></strong></p>
        </div>
        <div class="mb-5 rounded-xl p-3" style="background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.2)">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" id="use-ip-only" class="w-auto" onchange="toggleIPOnly()"/>
            <span class="text-yellow-300 text-sm font-medium">Use server IP instead of domain (HTTP only)</span>
          </label>
          <p class="text-slate-400 text-xs mt-1 ml-6">
            Skip DNS — app will be accessible at
            <span id="ip-only-preview" class="font-mono text-indigo-300">http://—</span>.
            SSL is not available for bare IP addresses.
          </p>
        </div>
        <div class="mb-4">
          <button onclick="checkDNS()" id="dns-btn"
            class="btn-primary text-white text-sm font-semibold rounded-xl px-5 py-2">
            Check DNS A record
          </button>
          <div id="dns-result" class="mt-3 text-sm hidden rounded-lg p-3"></div>
        </div>
        <div id="dns-instructions" class="hidden rounded-xl p-4 mb-4 text-sm"
          style="background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.2)">
          <p class="text-yellow-300 font-semibold mb-2">⚠ DNS not pointed at this server</p>
          <p class="text-slate-300 mb-2">Create an <strong>A record</strong> in your DNS provider:</p>
          <div class="font-mono text-xs bg-black/30 rounded p-2 text-green-300">
            <span id="dns-record-host"></span> → <span id="dns-record-ip"></span>
          </div>
          <p class="text-slate-400 text-xs mt-2">DNS can take up to 24 h to propagate. You can continue but SSL setup may fail.</p>
        </div>
        <div class="flex justify-between mt-4">
          <button onclick="goTo(2)" class="text-slate-400 hover:text-white text-sm px-4 py-2">← Back</button>
          <button onclick="goTo(4)" id="domain-next" class="btn-primary text-white font-semibold rounded-xl px-6 py-2.5">Continue →</button>
        </div>
      </div>

      <!-- STEP 4: Database -->
      <div class="step-panel" id="panel-4">
        <h2 class="text-xl font-bold text-white mb-1">Database (MongoDB)</h2>
        <p class="text-slate-400 text-sm mb-6">Choose where MongoDB will run.</p>
        <div class="mb-6">
          <label class="text-slate-300 text-sm mb-2 block">MongoDB location</label>
          <select id="mongo-type" onchange="toggleMongoRemote()">
            <option value="local">Local — run MongoDB in Docker on this server (recommended)</option>
            <option value="remote" id="mongo-remote-opt">Remote — use an external MongoDB URI</option>
          </select>
          <p id="mongo-plan-note" class="text-slate-500 text-xs mt-2 hidden">
            Remote MongoDB is not available on your plan. Upgrade to Professional or Enterprise.
          </p>
        </div>
        <div id="mongo-remote-row" class="hidden mb-4">
          <label class="text-slate-300 text-sm mb-1 block">MongoDB URI</label>
          <input id="mongo-uri" placeholder="mongodb+srv://user:pass@cluster.mongodb.net/email_marketing"/>
          <button onclick="testMongo()" class="mt-2 text-sm text-indigo-400 hover:text-indigo-300">Test connection</button>
          <div id="mongo-test-result" class="mt-2 text-sm hidden"></div>
        </div>
        <div class="flex justify-between mt-6">
          <button onclick="goTo(3)" class="text-slate-400 hover:text-white text-sm px-4 py-2">← Back</button>
          <button onclick="goTo(5)" class="btn-primary text-white font-semibold rounded-xl px-6 py-2.5">Continue →</button>
        </div>
      </div>

      <!-- STEP 5: Redis -->
      <div class="step-panel" id="panel-5">
        <h2 class="text-xl font-bold text-white mb-1">Cache & Queue (Redis)</h2>
        <p class="text-slate-400 text-sm mb-6">Redis is used for job queues, caching, and rate limiting.</p>
        <div class="mb-6">
          <label class="text-slate-300 text-sm mb-2 block">Redis location</label>
          <select id="redis-type" onchange="toggleRedisRemote()">
            <option value="local">Local — run Redis in Docker on this server (recommended)</option>
            <option value="remote" id="redis-remote-opt">Remote — use an external Redis URL</option>
          </select>
          <p id="redis-plan-note" class="text-slate-500 text-xs mt-2 hidden">Remote Redis is not available on your plan.</p>
        </div>
        <div id="redis-remote-row" class="hidden mb-4">
          <label class="text-slate-300 text-sm mb-1 block">Redis URL</label>
          <input id="redis-url" placeholder="redis://default:password@hostname:6379/0"/>
          <button onclick="testRedis()" class="mt-2 text-sm text-indigo-400 hover:text-indigo-300">Test connection</button>
          <div id="redis-test-result" class="mt-2 text-sm hidden"></div>
        </div>
        <div class="flex justify-between mt-6">
          <button onclick="goTo(4)" class="text-slate-400 hover:text-white text-sm px-4 py-2">← Back</button>
          <button onclick="goTo(6)" class="btn-primary text-white font-semibold rounded-xl px-6 py-2.5">Continue →</button>
        </div>
      </div>

      <!-- STEP 6: Admin User -->
      <div class="step-panel" id="panel-6">
        <h2 class="text-xl font-bold text-white mb-1">Create admin account</h2>
        <p class="text-slate-400 text-sm mb-6">This is the account you'll use to log in. Self-registration is disabled after setup.</p>
        <div class="space-y-4">
          <div>
            <label class="text-slate-300 text-sm mb-1 block">Full name</label>
            <input id="admin-name" placeholder="Jane Smith"/>
          </div>
          <div>
            <label class="text-slate-300 text-sm mb-1 block">Email address</label>
            <input id="admin-email" type="email" placeholder="admin@yourcompany.com"/>
          </div>
          <div>
            <label class="text-slate-300 text-sm mb-1 block">Password</label>
            <input id="admin-password" type="password" placeholder="Min. 8 characters"/>
          </div>
          <div>
            <label class="text-slate-300 text-sm mb-1 block">Confirm password</label>
            <input id="admin-confirm" type="password" placeholder="Repeat password"/>
          </div>
        </div>
        <div id="admin-error" class="hidden text-red-400 text-sm mt-3 bg-red-900/20 rounded-lg p-3"></div>
        <div class="flex justify-between mt-6">
          <button onclick="goTo(5)" class="text-slate-400 hover:text-white text-sm px-4 py-2">← Back</button>
          <button onclick="goTo(7)" class="btn-primary text-white font-semibold rounded-xl px-6 py-2.5">Continue →</button>
        </div>
      </div>

      <!-- STEP 7: Review -->
      <div class="step-panel" id="panel-7">
        <h2 class="text-xl font-bold text-white mb-1">Review &amp; Install</h2>
        <p class="text-slate-400 text-sm mb-6">Check everything below then click <strong class="text-white">Install Now</strong>.</p>
        <div id="review-content" class="space-y-2 mb-6 text-sm"></div>
        <div class="flex items-center gap-2 mb-4">
          <input type="checkbox" id="skip-ssl" class="w-auto"/>
          <label for="skip-ssl" class="text-slate-400 text-sm">
            Skip SSL / Let's Encrypt (run on HTTP only — not recommended for production)
          </label>
        </div>
        <div class="flex justify-between">
          <button onclick="goTo(6)" class="text-slate-400 hover:text-white text-sm px-4 py-2">← Back</button>
          <button onclick="startInstall()" id="install-btn"
            class="btn-primary text-white font-bold rounded-xl px-8 py-3 text-base">
            🚀 Install Now
          </button>
        </div>
      </div>

      <!-- STEP 8: Installing -->
      <div class="step-panel" id="panel-8">
        <h2 class="text-xl font-bold text-white mb-1">Installing…</h2>
        <p class="text-slate-400 text-sm mb-4">Please wait. This typically takes 3–8 minutes.</p>
        <div id="progress-log" class="bg-black/40 rounded-xl p-4 h-72 overflow-y-auto font-mono text-xs space-y-0.5 border border-white/5">
          <div class="log-line log-info">Connecting to server…</div>
        </div>
        <div id="install-done-section" class="hidden mt-6 text-center">
          <div class="text-5xl mb-3">🎉</div>
          <h3 class="text-xl font-bold text-white mb-2">Installation complete!</h3>
          <p class="text-slate-400 mb-4">Your platform is live. Click below to open the dashboard.</p>
          <a id="open-app-btn" href="#" target="_blank"
            class="btn-primary inline-block text-white font-bold rounded-xl px-8 py-3">
            Open Dashboard →
          </a>
        </div>
        <div id="install-error-section" class="hidden mt-4 text-red-400 text-sm bg-red-900/20 rounded-xl p-4">
          Installation encountered errors. Check the log above.<br/>
          Fix the issue and re-run <code>python3 setup_server.py</code>.
        </div>
      </div>

    </div>
  </div>

  <p class="text-center text-slate-600 text-xs mt-6">
    ZeniPost Self-Hosted · <a href="https://docs.zenipost.com" target="_blank" class="hover:text-slate-400">Documentation</a>
  </p>
</div>

<script>
const STEPS = ['Pre-flight','License','Domain','Database','Redis','Admin','Review','Installing'];
let currentStep = 1;
let licenseData = null;
let features = {};
let dnsOk = false;

function renderStepDots() {
  const el = document.getElementById('step-indicators');
  el.innerHTML = STEPS.map((label, i) => {
    const n = i + 1;
    let cls = n < currentStep ? 'done' : n === currentStep ? 'active' : 'pending';
    const icon = n < currentStep ? '✓' : n;
    const connector = i < STEPS.length - 1
      ? `<div class="h-px w-8 ${n < currentStep ? 'bg-emerald-500' : 'bg-slate-700'}" style="margin-top:14px"></div>`
      : '';
    return `<div class="flex flex-col items-center" style="min-width:56px">
      <div class="step-dot w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-bold ${cls}">${icon}</div>
      <span class="text-xs mt-1 ${n===currentStep?'text-slate-300':'text-slate-600'}">${label}</span>
    </div>${connector}`;
  }).join('');
}

function goTo(n) {
  if (n === 7) { if (!buildReview()) return; }
  document.querySelectorAll('.step-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`panel-${n}`).classList.add('active');
  currentStep = n;
  renderStepDots();
  window.scrollTo({top:0,behavior:'smooth'});
}

renderStepDots();

async function runPreflight() {
  const el = document.getElementById('preflight-list');
  const ipEl = document.getElementById('pf-server-ip');
  const nextBtn = document.getElementById('pf-next');
  el.innerHTML = '<div class="text-slate-400 text-sm animate-pulse">Running checks…</div>';
  nextBtn.disabled = true;

  const res = await api('/api/preflight', {});
  if (!res.checks) {
    el.innerHTML = '<div class="text-red-400 text-sm">Could not connect to setup server.</div>';
    return;
  }

  if (res.public_ip)   ipEl.textContent = res.public_ip;
  if (res.instance_id) document.getElementById('pf-instance').textContent = res.instance_id;
  if (res.region)      document.getElementById('pf-region').textContent   = res.region;

  el.innerHTML = res.checks.map(c => `
    <div class="flex items-start gap-3 py-2 border-b border-white/5">
      <span class="${c.ok ? 'text-emerald-400' : 'text-red-400'} text-base mt-0.5">${c.ok ? '✓' : '✗'}</span>
      <div>
        <p class="text-slate-200 text-sm font-medium">${c.name}</p>
        <p class="text-slate-500 text-xs">${c.detail}</p>
      </div>
    </div>`).join('');

  const allOk = res.checks.every(c => c.ok);
  nextBtn.disabled = false;
  nextBtn.textContent = allOk ? 'All checks passed — Continue →' : 'Continue anyway →';
  nextBtn.className = allOk
    ? 'btn-primary text-white font-semibold rounded-xl px-6 py-2.5'
    : 'bg-yellow-600 hover:bg-yellow-500 text-white font-semibold rounded-xl px-6 py-2.5 transition-opacity';
  document.getElementById('sg-port').textContent = res.setup_port || '8080';
}

window.addEventListener('load', () => setTimeout(runPreflight, 400));

document.getElementById('license-file').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => { document.getElementById('license-json').value = ev.target.result; };
  reader.readAsText(file);
});

async function validateLicense() {
  const raw = document.getElementById('license-json').value.trim();
  const errEl = document.getElementById('license-error');
  const sumEl = document.getElementById('license-summary');
  errEl.classList.add('hidden');
  sumEl.classList.add('hidden');

  if (!raw) { showErr(errEl, 'Please paste or upload your license.json'); return; }

  let parsed;
  try { parsed = JSON.parse(raw); }
  catch(e) { showErr(errEl, 'Invalid JSON: ' + e.message); return; }

  const res = await api('/api/validate-license', { license: parsed });
  if (!res.ok) { showErr(errEl, res.error); return; }

  licenseData = parsed;
  features    = res.features;

  const planColors = {starter:'text-slate-300',professional:'text-indigo-300',enterprise:'text-yellow-300'};
  const planColor  = planColors[res.plan] || 'text-white';
  const featList   = Object.entries(res.features)
    .filter(([k]) => ['ab_testing','automation','remote_db','remote_redis','api_access','deliverability_dashboard'].includes(k))
    .map(([k,v]) => {
      const label = k.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
      return `<span class="feature-badge ${v?'badge-green':'badge-gray'}">${v?'✓':'✗'} ${label}</span>`;
    }).join(' ');

  sumEl.innerHTML = `
    <div class="flex items-center gap-3 mb-3">
      <span class="text-2xl">✅</span>
      <div>
        <p class="text-white font-semibold">License valid</p>
        <p class="text-slate-400 text-xs">${res.issued_to || ''}  ·  Expires: ${parsed.expires_at || '—'}</p>
      </div>
    </div>
    <p class="text-sm mb-2">Plan: <strong class="${planColor}">${res.plan.toUpperCase()}</strong></p>
    <div class="flex flex-wrap gap-1">${featList}</div>`;
  sumEl.classList.remove('hidden');

  const dom = parsed.domain || '';
  document.getElementById('licensed-domain').value = dom;
  document.getElementById('sub-domain-suffix').textContent = dom;
  document.getElementById('sub-example').textContent = 'app.' + dom;
  document.getElementById('final-domain').textContent = dom;

  if (!features.remote_db)    { document.getElementById('mongo-remote-opt').disabled = true; }
  if (!features.remote_redis) { document.getElementById('redis-remote-opt').disabled = true; }

  setTimeout(() => goTo(3), 600);
}

function _isIPAddress(s) {
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(s.trim());
}

function toggleSubdomain() {
  if (document.getElementById('use-ip-only').checked) return;
  const checked = document.getElementById('use-subdomain').checked;
  document.getElementById('subdomain-row').classList.toggle('hidden', !checked);
  updateSubdomainPreview();
}

function updateSubdomainPreview() {
  if (document.getElementById('use-ip-only').checked) return;
  const base   = document.getElementById('licensed-domain').value || '';
  const prefix = document.getElementById('subdomain-prefix').value.trim();
  const checked = document.getElementById('use-subdomain').checked;
  const domain  = (checked && prefix) ? `${prefix}.${base}` : base;
  document.getElementById('final-domain').textContent = domain;
}

function toggleIPOnly() {
  const checked  = document.getElementById('use-ip-only').checked;
  const publicIp = document.getElementById('pf-server-ip').textContent.trim();
  const hasIp    = publicIp && publicIp !== 'detecting…' && publicIp !== '—';
  const ipToUse  = hasIp ? publicIp : '';

  if (checked) {
    document.getElementById('use-subdomain').checked = false;
    document.getElementById('subdomain-row').classList.add('hidden');
    document.getElementById('final-domain').textContent = ipToUse || '(detecting IP…)';
    document.getElementById('ip-only-preview').textContent = ipToUse ? ('http://' + ipToUse) : '—';
    const skipSslEl = document.getElementById('skip-ssl');
    if (skipSslEl) skipSslEl.checked = true;
    document.getElementById('dns-result').classList.add('hidden');
    document.getElementById('dns-instructions').classList.add('hidden');
  } else {
    document.getElementById('ip-only-preview').textContent = '—';
    const skipSslEl = document.getElementById('skip-ssl');
    if (skipSslEl) skipSslEl.checked = false;
    updateSubdomainPreview();
  }
}

function getFinalDomain() {
  return document.getElementById('final-domain').textContent.trim();
}

async function checkDNS() {
  const domain = getFinalDomain();
  if (!domain) return;
  const btn = document.getElementById('dns-btn');
  btn.textContent = 'Checking…'; btn.disabled = true;
  const res = await api('/api/check-dns', { domain });
  btn.textContent = 'Check DNS A record'; btn.disabled = false;

  const resEl  = document.getElementById('dns-result');
  const instEl = document.getElementById('dns-instructions');
  resEl.classList.remove('hidden');
  instEl.classList.add('hidden');

  if (res.matches) {
    resEl.className = 'mt-3 text-sm rounded-lg p-3 text-emerald-400 bg-emerald-900/20';
    resEl.textContent = `✓ ${domain} → ${res.resolved_ip} — matches this server`;
    dnsOk = true;
  } else {
    resEl.className = 'mt-3 text-sm rounded-lg p-3 text-yellow-400 bg-yellow-900/20';
    resEl.textContent = res.resolved_ip
      ? `⚠ ${domain} resolves to ${res.resolved_ip}, but this server is ${res.server_ip}`
      : `⚠ ${domain} could not be resolved — DNS may not have propagated`;
    dnsOk = false;
    document.getElementById('dns-record-host').textContent = domain;
    document.getElementById('dns-record-ip').textContent   = res.server_ip || '<your-server-ip>';
    instEl.classList.remove('hidden');
  }
}

function toggleMongoRemote() {
  const isRemote = document.getElementById('mongo-type').value === 'remote';
  document.getElementById('mongo-remote-row').classList.toggle('hidden', !isRemote);
  document.getElementById('mongo-plan-note').classList.toggle('hidden', features.remote_db !== false);
}

async function testMongo() {
  const uri = document.getElementById('mongo-uri').value.trim();
  const el  = document.getElementById('mongo-test-result');
  el.classList.remove('hidden'); el.textContent = 'Testing…'; el.className='mt-2 text-sm text-slate-400';
  const res = await api('/api/test-mongo', { uri });
  el.textContent = res.ok ? '✓ Connection successful' : '✗ ' + res.error;
  el.className = 'mt-2 text-sm ' + (res.ok ? 'text-emerald-400' : 'text-red-400');
}

function toggleRedisRemote() {
  const isRemote = document.getElementById('redis-type').value === 'remote';
  document.getElementById('redis-remote-row').classList.toggle('hidden', !isRemote);
}

async function testRedis() {
  const url = document.getElementById('redis-url').value.trim();
  const el  = document.getElementById('redis-test-result');
  el.classList.remove('hidden'); el.textContent = 'Testing…'; el.className='mt-2 text-sm text-slate-400';
  const res = await api('/api/test-redis', { url });
  el.textContent = res.ok ? '✓ Connection successful' : '✗ ' + res.error;
  el.className = 'mt-2 text-sm ' + (res.ok ? 'text-emerald-400' : 'text-red-400');
}

function buildReview() {
  const errEl = document.getElementById('admin-error');
  errEl.classList.add('hidden');

  const name  = document.getElementById('admin-name').value.trim();
  const email = document.getElementById('admin-email').value.trim();
  const pw    = document.getElementById('admin-password').value;
  const pw2   = document.getElementById('admin-confirm').value;

  if (!name)               { showErr(errEl,'Name is required'); goTo(6); return false; }
  if (!email.includes('@')){ showErr(errEl,'Enter a valid email'); goTo(6); return false; }
  if (pw.length < 8)       { showErr(errEl,'Password must be at least 8 characters'); goTo(6); return false; }
  if (pw !== pw2)          { showErr(errEl,'Passwords do not match'); goTo(6); return false; }

  const domain     = getFinalDomain();
  const mongoLocal = document.getElementById('mongo-type').value === 'local';
  const redisLocal = document.getElementById('redis-type').value === 'local';

  const rows = [
    ['Plan',    (licenseData?.plan || '—').toUpperCase()],
    ['Domain',  domain],
    ['MongoDB', mongoLocal ? 'Local Docker' : (document.getElementById('mongo-uri').value.slice(0,50)+'…')],
    ['Redis',   redisLocal ? 'Local Docker' : (document.getElementById('redis-url').value.slice(0,50)+'…')],
    ['Admin',   email],
  ];
  document.getElementById('review-content').innerHTML = rows.map(([k,v]) =>
    `<div class="flex gap-3 p-2.5 rounded-lg" style="background:rgba(255,255,255,.03)">
       <span class="text-slate-500 w-24 shrink-0">${k}</span>
       <span class="text-white font-medium">${v}</span>
     </div>`
  ).join('');
  return true;
}

async function startInstall() {
  goTo(8);
  const logEl = document.getElementById('progress-log');
  logEl.innerHTML = '';

  const domain     = getFinalDomain();
  const domainIsIp = _isIPAddress(domain);
  const payload = {
    domain:         domain,
    mongo_local:    document.getElementById('mongo-type').value === 'local',
    mongo_uri:      document.getElementById('mongo-uri').value.trim(),
    redis_local:    document.getElementById('redis-type').value === 'local',
    redis_url:      document.getElementById('redis-url').value.trim(),
    admin_name:     document.getElementById('admin-name').value.trim(),
    admin_email:    document.getElementById('admin-email').value.trim(),
    admin_password: document.getElementById('admin-password').value,
    skip_ssl:       document.getElementById('skip-ssl').checked || domainIsIp,
    license:        licenseData,
  };

  const startRes = await api('/api/install', payload);
  if (!startRes.ok) {
    const logEl = document.getElementById('progress-log');
    const div = document.createElement('div');
    div.className = 'log-line log-error';
    div.textContent = 'Error: ' + (startRes.error || 'Unknown error');
    logEl.appendChild(div);
    document.getElementById('install-error-section').classList.remove('hidden');
    return;
  }

  const evtSource = new EventSource('/api/progress');
  evtSource.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.msg === '__keepalive__') return;

    const div = document.createElement('div');
    div.className = 'log-line log-' + (data.level || 'info');
    div.textContent = data.msg;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;

    if (data.level === 'done') {
      evtSource.close();
      showDone(data.app_url || '');
    } else if (data.level === 'error' && data.msg.startsWith('INSTALL FAILED')) {
      evtSource.close();
      document.getElementById('install-error-section').classList.remove('hidden');
    }
  };
  evtSource.onerror = () => evtSource.close();
}

function showDone(appUrl) {
  document.getElementById('install-done-section').classList.remove('hidden');
  const finalUrl = appUrl
    || session.app_url
    || window.location.origin.replace(':' + (window.location.port || '8080'), '');
  document.getElementById('open-app-btn').href = finalUrl || '/';
}

let session = {};
async function api(path, body = {}) {
  try {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (data.app_url) session.app_url = data.app_url;
    return data;
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

function showErr(el, msg) {
  el.textContent = msg;
  el.classList.remove('hidden');
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class SetupHandler(BaseHTTPRequestHandler):
    server_version = "ZeniPost-Setup/1.0"

    def log_message(self, fmt, *args):
        log.debug("HTTP %s", fmt % args)

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200) -> None:
        body = json.dumps(data).encode()
        self._send(code, "application/json", body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if SETUP_LOCK.exists() and path not in ("/api/status",):
            try:
                info = json.loads(SETUP_LOCK.read_text())
                url  = info.get("url", "/")
            except Exception:
                url = "/"
            self.send_response(302)
            self.send_header("Location", url)
            self.end_headers()
            return

        if path == "/":
            app_url = session_get("app_url", "#")
            html = HTML.replace("___APP_URL___", app_url)
            self._send(200, "text/html; charset=utf-8", html.encode())
        elif path == "/api/progress":
            self._sse_stream()
        elif path == "/api/status":
            complete = SETUP_LOCK.exists()
            url = ""
            if complete:
                try:
                    url = json.loads(SETUP_LOCK.read_text()).get("url", "")
                except Exception:
                    pass
            self._json({"complete": complete, "url": url})
        else:
            self._send(404, "text/plain", b"Not found")

    def _sse_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                try:
                    item = _progress_queue.get(timeout=15)
                    data = json.dumps(item)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                    if item.get("msg") == "DONE" or (
                        item.get("level") == "error"
                        and "INSTALL FAILED" in item.get("msg", "")
                    ):
                        break
                except Exception:
                    self.wfile.write(b'data: {"msg":"__keepalive__"}\n\n')
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_body()

        routes = {
            "/api/preflight":        self._api_preflight,
            "/api/validate-license": self._api_validate_license,
            "/api/check-dns":        self._api_check_dns,
            "/api/test-mongo":       self._api_test_mongo,
            "/api/test-redis":       self._api_test_redis,
            "/api/install":          self._api_install,
        }
        handler = routes.get(path)
        if handler:
            try:
                handler(body)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
        else:
            self._send(404, "text/plain", b"Not found")

    def _api_preflight(self, body: dict) -> None:
        self._json(run_preflight())

    def _api_validate_license(self, body: dict) -> None:
        data = body.get("license", {})
        ok, err, feats = validate_license(data)
        if not ok:
            self._json({"ok": False, "error": err})
            return
        # Write to BOTH locations so the backend container finds it at /app/license.json
        _write_license(data)
        self._json({
            "ok":        True,
            "plan":      data.get("plan", "starter"),
            "issued_to": data.get("issued_to", ""),
            "features":  feats,
        })

    def _api_check_dns(self, body: dict) -> None:
        domain = body.get("domain", "").strip()
        matches, server_ip, resolved_ip = check_dns_record(domain)
        self._json({
            "ok":          True,
            "matches":     matches,
            "server_ip":   server_ip,
            "resolved_ip": resolved_ip,
        })

    def _api_test_mongo(self, body: dict) -> None:
        uri = body.get("uri", "").strip()
        ok, err = test_mongo(uri)
        self._json({"ok": ok, "error": err})

    def _api_test_redis(self, body: dict) -> None:
        url = body.get("url", "").strip()
        ok, err = test_redis(url)
        self._json({"ok": ok, "error": err})

    def _api_install(self, body: dict) -> None:
        if SETUP_LOCK.exists():
            self._json({"ok": False, "error": "Setup already complete."})
            return

        # ── Require a valid license ───────────────────────────────────────────
        lic_data = body.get("license") or {}
        if not lic_data:
            self._json({
                "ok":    False,
                "error": "No license provided. Please complete the License step before installing.",
            })
            return

        lic_ok, lic_err, _ = validate_license(lic_data)
        if not lic_ok:
            self._json({"ok": False, "error": f"License validation failed: {lic_err}"})
            return

        # Ensure both license.json copies exist on disk
        _write_license(lic_data)

        # ── Domain vs. license enforcement ────────────────────────────────────
        install_domain = body.get("domain", "").strip().lower()
        lic_domain     = lic_data.get("domain", "").strip().lower()
        lic_root       = lic_data.get("root_domain", "").strip().lower()

        if install_domain and lic_domain and not _is_ip_address(install_domain):
            domain_ok = (
                install_domain == lic_domain
                or (lic_root and (
                    install_domain == lic_root
                    or install_domain.endswith("." + lic_root)
                ))
            )
            if not domain_ok:
                self._json({
                    "ok":    False,
                    "error": (
                        f"The chosen domain '{install_domain}' does not match the "
                        f"licensed domain '{lic_domain}'. "
                        "Download a license issued for this domain from the ZeniPost Dashboard."
                    ),
                })
                return

        # ── Mongo password: reuse existing to survive retries ─────────────────
        env_path       = INSTALL_DIR / "backend" / ".env"
        mongo_password = _extract_mongo_password(env_path) or _gen_mongo_password()

        config = {
            "domain":         body.get("domain", ""),
            "mongo_local":    body.get("mongo_local", True),
            "mongo_uri":      body.get("mongo_uri", ""),
            "redis_local":    body.get("redis_local", True),
            "redis_url":      body.get("redis_url", ""),
            "admin_name":     body.get("admin_name", "Admin"),
            "admin_email":    body.get("admin_email", ""),
            "admin_password": body.get("admin_password", ""),
            "skip_ssl":       body.get("skip_ssl", False),
            "mongo_password": mongo_password,
            "license":        lic_data,   # passed to run_install for step 1b
        }
        session_set(**{k: v for k, v in config.items() if k != "admin_password"})

        while not _progress_queue.empty():
            try:
                _progress_queue.get_nowait()
            except Exception:
                break

        t = threading.Thread(target=run_install, args=(config,), daemon=True)
        t.start()
        self._json({"ok": True, "msg": "Installation started"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global _server_ref, _SETUP_PORT

    parser = argparse.ArgumentParser(description="ZeniPost Browser Setup Wizard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    _SETUP_PORT = args.port
    _load_session()

    if SETUP_LOCK.exists():
        try:
            info = json.loads(SETUP_LOCK.read_text())
            url  = info.get("url", "")
            print(f"\n  Setup is already complete. App is at: {url}")
            print(f"  Setup wizard service stopping.\n")
        except Exception:
            pass
        sys.exit(0)

    public_ip = _get_public_ip() or ""
    local_ip  = "localhost"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
    except Exception:
        pass

    display_ip = public_ip or local_ip

    try:
        server = HTTPServer((args.host, args.port), SetupHandler)
    except OSError as exc:
        print(f"\n  ERROR: Cannot bind to port {args.port}: {exc}")
        print(f"  Try:  python3 setup_server.py --port 8081\n")
        sys.exit(1)

    _server_ref = server

    print(f"""
  ╔══════════════════════════════════════════════════════╗
  ║   ZeniPost  —  EC2 Setup Wizard                      ║
  ╠══════════════════════════════════════════════════════╣
  ║                                                      ║
  ║   Open in your browser:                              ║
  ║                                                      ║
  ║     http://{display_ip}:{args.port}
  ║                                                      ║
  ║   EC2 Security Group — open inbound:                 ║
  ║     TCP {args.port}  (setup wizard, your IP only)         ║
  ║     TCP 80   (HTTP / Let's Encrypt)                  ║
  ║     TCP 443  (HTTPS after setup)                     ║
  ║                                                      ║
  ║   Wizard stops itself when setup is done.            ║
  ╚══════════════════════════════════════════════════════╝
""")
    log.info("Setup wizard listening on %s:%s", args.host, args.port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped by user (Ctrl+C).")

    if _shutdown_event.is_set():
        print("\n  Installation complete — wizard shut down cleanly.")
        print("  Your app is live. You can now close port 8080 in your Security Group.\n")


if __name__ == "__main__":
    main()