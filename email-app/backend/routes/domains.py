# backend/app/routers/domains.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, validator
from typing import List, Optional
from datetime import datetime
import re
import dns.resolver
import secrets
import string
from bson import ObjectId
from database import get_domains_collection
from models.domain import Domain, DomainCreate, DomainResponse, VerificationRecords

router = APIRouter(tags=["domains"])

async def create_domain(domain_data: dict):
    collection = get_domains_collection()
    result = await collection.insert_one(domain_data)
    return str(result.inserted_id)

class DomainVerificationService:
    @staticmethod
    def generate_verification_token() -> str:
        """Generate a random verification token"""
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    
    @staticmethod
    def generate_dkim_keys():
        """Generate DKIM keys (simplified for demo - use proper crypto in production)"""
        # In production, use cryptography library to generate proper RSA keys
        private_key = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        public_key = f"v=DKIM1; k=rsa; p={private_key}MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC..."
        return private_key, public_key
    
    @staticmethod
    def create_verification_records(domain: str) -> VerificationRecords:
        """Create DNS verification records for a domain"""
        verification_token = DomainVerificationService.generate_verification_token()
        dkim_private, dkim_public = DomainVerificationService.generate_dkim_keys()
        
        return VerificationRecords(
            domain=domain,
            verification_token=verification_token,
            spf_record=f"v=spf1 include:emailmarketing.yourapp.com ~all",
            dkim_selector="emailmarketing",
            dkim_record=dkim_public,
            dmarc_record=f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}; ruf=mailto:dmarc@{domain}; rf=afrf; pct=100"
        )
    
    @staticmethod
    def verify_dns_records(domain: str, verification_records: VerificationRecords) -> dict:
        """Verify DNS records for domain"""
        results = {
            "verification_token": False,
            "spf_record": False,
            "dkim_record": False,
            "dmarc_record": False,
            "overall_status": False
        }
        
        try:
            # Check verification token
            try:
                txt_records = dns.resolver.resolve(f"_emailverify.{domain}", 'TXT')
                for record in txt_records:
                    if verification_records.verification_token in str(record):
                        results["verification_token"] = True
                        break
            except:
                pass
            
            # Check SPF record
            try:
                txt_records = dns.resolver.resolve(domain, 'TXT')
                for record in txt_records:
                    record_str = str(record).strip('"')
                    if record_str.startswith('v=spf1') and 'emailmarketing.yourapp.com' in record_str:
                        results["spf_record"] = True
                        break
            except:
                pass
            
            # Check DKIM record
            try:
                dkim_domain = f"{verification_records.dkim_selector}._domainkey.{domain}"
                txt_records = dns.resolver.resolve(dkim_domain, 'TXT')
                for record in txt_records:
                    if 'v=DKIM1' in str(record):
                        results["dkim_record"] = True
                        break
            except:
                pass
            
            # Check DMARC record
            try:
                txt_records = dns.resolver.resolve(f"_dmarc.{domain}", 'TXT')
                for record in txt_records:
                    if 'v=DMARC1' in str(record):
                        results["dmarc_record"] = True
                        break
            except:
                pass
            
            # Overall status - require verification token + at least SPF
            results["overall_status"] = results["verification_token"] and results["spf_record"]
            
        except Exception as e:
            print(f"DNS verification error: {e}")
        
        return results

@router.post("/", response_model=DomainResponse)
async def add_domain(domain_data: DomainCreate):
    """Add a new domain for verification"""
    collection = get_domains_collection()
    domain = domain_data.domain.lower().strip()
    
    # Validate domain format
    domain_regex = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
    if not re.match(domain_regex, domain):
        raise HTTPException(status_code=400, detail="Invalid domain format")
    
    # Check if domain already exists
    existing_domain = await collection.find_one({"domain": domain})
    if existing_domain:
        raise HTTPException(status_code=400, detail="Domain already exists")
    
    # Create verification records
    verification_records = DomainVerificationService.create_verification_records(domain)
    
    # Create domain document
    domain_doc = {
        "domain": domain,
        "status": "pending",
        "verification_records": verification_records.dict(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    # Insert into database
    result = await collection.insert_one(domain_doc)
    domain_doc["id"] = str(result.inserted_id)
    domain_doc["_id"] = result.inserted_id
    
    return DomainResponse(**domain_doc)

@router.get("/", response_model=List[DomainResponse])
async def get_domains():
    """Get all domains for the user"""
    collection = get_domains_collection()
    cursor = collection.find({}).sort("created_at", -1)
    domains = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        domains.append(DomainResponse(**doc))
    return domains

@router.get("/{domain_id}/verification-records")
async def get_verification_records(domain_id: str):
    """Get verification records for a domain"""
    collection = get_domains_collection()
    try:
        domain_object_id = ObjectId(domain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid domain ID")
    
    domain = await collection.find_one({"_id": domain_object_id})
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    return {"verification_records": domain["verification_records"]}

@router.post("/{domain_id}/verify")
async def verify_domain(domain_id: str):
    """Verify domain DNS records"""
    collection = get_domains_collection()
    try:
        domain_object_id = ObjectId(domain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid domain ID")
    
    domain = await collection.find_one({"_id": domain_object_id})
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    # Create verification records object
    verification_records = VerificationRecords(**domain["verification_records"])
    
    # Verify DNS records
    verification_results = DomainVerificationService.verify_dns_records(
        domain["domain"],
        verification_records
    )
    
    # Update domain status based on verification results
    new_status = "verified" if verification_results["overall_status"] else "failed"
    
    # Update in database
    await collection.update_one(
        {"_id": domain_object_id},
        {
            "$set": {
                "status": new_status,
                "verification_results": verification_results,
                "updated_at": datetime.utcnow(),
                "verified_at": datetime.utcnow() if new_status == "verified" else None
            }
        }
    )
    
    return {
        "status": new_status,
        "verification_results": verification_results,
        "message": "Domain verified successfully!" if new_status == "verified" else "Domain verification failed. Please check DNS records."
    }

@router.delete("/{domain_id}")
async def delete_domain(domain_id: str):
    """Delete a domain"""
    collection = get_domains_collection()
    try:
        domain_object_id = ObjectId(domain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid domain ID")
    
    result = await collection.delete_one({"_id": domain_object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    return {"message": "Domain deleted successfully"}

@router.post("/{domain_id}/regenerate-records")
async def regenerate_verification_records(domain_id: str):
    """Regenerate verification records for a domain"""
    collection = get_domains_collection()
    try:
        domain_object_id = ObjectId(domain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid domain ID")
    
    domain = await collection.find_one({"_id": domain_object_id})
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    # Generate new verification records
    verification_records = DomainVerificationService.create_verification_records(domain["domain"])
    
    # Update in database
    await collection.update_one(
        {"_id": domain_object_id},
        {
            "$set": {
                "verification_records": verification_records.dict(),
                "status": "pending",
                "updated_at": datetime.utcnow()
            },
            "$unset": {"verification_results": "", "verified_at": ""}
        }
    )
    
    return {
        "message": "Verification records regenerated successfully",
        "verification_records": verification_records.dict()
    }

