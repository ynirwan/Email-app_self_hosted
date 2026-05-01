"""
backend/routes/domains.py

All responses return plain dicts — no Pydantic response_model that could fail
validation and cause FastAPI to drop the route silently.

Routes
------
POST   /                         add domain
GET    /                         list all domains
GET    /verified                 verified domains only (for from-email picker)
GET    /{domain_id}/verification-records
POST   /{domain_id}/verify
POST   /{domain_id}/subdomain    set / clear tracking subdomain
POST   /{domain_id}/regenerate-records
DELETE /{domain_id}
"""

import logging
import re
import socket
import os
import secrets
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_domains_collection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["domains"])


# ─── request bodies ──────────────────────────────────────────────────────────

class DomainCreate(BaseModel):
    domain: str

class SubdomainUpdate(BaseModel):
    tracking_subdomain: Optional[str] = None


# ─── helpers ─────────────────────────────────────────────────────────────────

_DOMAIN_RE = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
)
_LABEL_RE = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$')


def _effective(domain: str, subdomain) -> str:
    return f"{subdomain}.{domain}" if subdomain else domain


def _doc(raw: dict) -> dict:
    """Serialize a Mongo document to a JSON-safe dict."""
    sub = raw.get("tracking_subdomain") or None
    return {
        "id":                  str(raw["_id"]),
        "domain":              raw["domain"],
        "status":              raw.get("status", "pending"),
        "tracking_subdomain":  sub,
        "effective_domain":    _effective(raw["domain"], sub),
        "verification_records": raw.get("verification_records"),
        "created_at":          raw["created_at"].isoformat(),
        "updated_at":          raw["updated_at"].isoformat(),
    }


def _make_vr(domain: str) -> dict:
    token = secrets.token_hex(16)
    return {
        "verification_token": f"zenipost-verify={token}",
    }


def _check_dns(domain: str, vr: dict) -> dict:
    results = {
        "verification_token": False,
        "overall_status":     False,
    }
    try:
        import dns.resolver  # type: ignore

        try:
            for r in dns.resolver.resolve(f"_emailverify.{domain}", "TXT"):
                if vr.get("verification_token", "") in str(r):
                    results["verification_token"] = True
                    break
        except Exception:
            pass

        results["overall_status"] = results["verification_token"]

    except ImportError:
        logger.warning("dnspython not installed; auto-verifying domain (dev mode)")
        results = {k: True for k in results}
    except Exception as exc:
        logger.error(f"DNS check failed for {domain}: {exc}")

    return results


# ─── routes ──────────────────────────────────────────────────────────────────

@router.post("")
async def add_domain(body: DomainCreate):
    col    = get_domains_collection()
    domain = body.domain.lower().strip()

    if not _DOMAIN_RE.match(domain):
        raise HTTPException(400, "Invalid domain format")

    if await col.find_one({"domain": domain}):
        raise HTTPException(400, "Domain already exists")

    vr  = _make_vr(domain)
    now = datetime.utcnow()
    raw = {
        "domain":             domain,
        "status":             "pending",
        "tracking_subdomain": None,
        "verification_records": vr,
        "created_at":         now,
        "updated_at":         now,
    }
    result  = await col.insert_one(raw)
    raw["_id"] = result.inserted_id
    return _doc(raw)


# NOTE: /verified MUST be declared before /{domain_id} so FastAPI doesn't
# treat the literal string "verified" as an ObjectId parameter.
@router.get("/verified")
async def get_verified_domains():
    """Verified domains list — consumed by the campaign from-email dropdown."""
    col = get_domains_collection()
    out = []
    async for raw in col.find({"status": "verified"}).sort("created_at", -1):
        sub = raw.get("tracking_subdomain") or None
        out.append({
            "id":               str(raw["_id"]),
            "domain":           raw["domain"],
            "tracking_subdomain": sub,
            "effective_domain": _effective(raw["domain"], sub),
        })
    return {"domains": out}

@router.get("/server-info")
async def get_server_info():
    """
    Return this server's public IP address so users know what
    A / CNAME record to add in their DNS for tracking domains.

    Resolution order:
      1. SERVER_PUBLIC_IP env var  (set this in production)
      2. X-Real-IP / HOST from a well-known IP service (httpbin / ipify)
      3. socket.gethostbyname fallback (usually private in containers)
    """
    import httpx

    public_ip = os.environ.get("SERVER_PUBLIC_IP", "").strip()

    if not public_ip:
        # Try to detect from external service
        for url in ("https://api.ipify.org", "https://ipv4.icanhazip.com"):
            try:
                async with httpx.AsyncClient(timeout=4) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        public_ip = r.text.strip()
                        break
            except Exception:
                continue

    if not public_ip:
        # Last-resort: hostname resolution (often a private/container IP)
        try:
            public_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            public_ip = "unknown"

    hostname = os.environ.get("SERVER_HOSTNAME", "").strip()

    return {
        "public_ip":   public_ip,
        "hostname":    hostname,   # e.g. "zenipost.example.com" if set
        "note": (
            "Point your tracking domain's A record to this IP address. "
            "If using a reverse proxy or load balancer, use its public IP instead. "
            "Set SERVER_PUBLIC_IP env var to override auto-detection."
        ),
    }


@router.get("")
async def list_domains():
    col = get_domains_collection()
    out = []
    async for raw in col.find({}).sort("created_at", -1):
        out.append(_doc(raw))
    return out


@router.get("/{domain_id}/verification-records")
async def get_verification_records(domain_id: str):
    col = get_domains_collection()
    try:
        oid = ObjectId(domain_id)
    except Exception:
        raise HTTPException(400, "Invalid domain ID")

    raw = await col.find_one({"_id": oid})
    if not raw:
        raise HTTPException(404, "Domain not found")

    return {"verification_records": raw.get("verification_records")}


@router.post("/{domain_id}/verify")
async def verify_domain(domain_id: str):
    col = get_domains_collection()
    try:
        oid = ObjectId(domain_id)
    except Exception:
        raise HTTPException(400, "Invalid domain ID")

    raw = await col.find_one({"_id": oid})
    if not raw:
        raise HTTPException(404, "Domain not found")

    vr      = raw.get("verification_records") or {}
    results = _check_dns(raw["domain"], vr)
    status  = "verified" if results["overall_status"] else "failed"
    now     = datetime.utcnow()

    update_fields = {"status": status, "verification_results": results, "updated_at": now}
    if status == "verified":
        update_fields["verified_at"] = now

    await col.update_one({"_id": oid}, {"$set": update_fields})

    return {
        "status":  status,
        "verification_results": results,
        "message": "Domain verified successfully!" if status == "verified"
                   else "Verification failed — check DNS records and try again.",
    }


@router.post("/{domain_id}/subdomain")
async def set_subdomain(domain_id: str, body: SubdomainUpdate):
    """Set or clear the tracking subdomain on a verified domain."""
    col = get_domains_collection()
    try:
        oid = ObjectId(domain_id)
    except Exception:
        raise HTTPException(400, "Invalid domain ID")

    raw = await col.find_one({"_id": oid})
    if not raw:
        raise HTTPException(404, "Domain not found")
    if raw.get("status") != "verified":
        raise HTTPException(400, "Subdomain can only be set on a verified domain")

    sub = (body.tracking_subdomain or "").strip().lower() or None
    if sub and not _LABEL_RE.match(sub):
        raise HTTPException(400, "Invalid subdomain — use a single label like 'track'")

    await col.update_one(
        {"_id": oid},
        {"$set": {"tracking_subdomain": sub, "updated_at": datetime.utcnow()}},
    )
    updated = await col.find_one({"_id": oid})
    return _doc(updated)


@router.post("/{domain_id}/regenerate-records")
async def regenerate_records(domain_id: str):
    col = get_domains_collection()
    try:
        oid = ObjectId(domain_id)
    except Exception:
        raise HTTPException(400, "Invalid domain ID")

    raw = await col.find_one({"_id": oid})
    if not raw:
        raise HTTPException(404, "Domain not found")

    vr  = _make_vr(raw["domain"])
    now = datetime.utcnow()
    await col.update_one(
        {"_id": oid},
        {
            "$set":   {"verification_records": vr, "status": "pending", "updated_at": now},
            "$unset": {"verification_results": "", "verified_at": ""},
        },
    )
    return {"message": "Verification records regenerated", "verification_records": vr}


@router.delete("/{domain_id}")
async def delete_domain(domain_id: str):
    col = get_domains_collection()
    try:
        oid = ObjectId(domain_id)
    except Exception:
        raise HTTPException(400, "Invalid domain ID")

    result = await col.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Domain not found")

    return {"message": "Domain deleted"}