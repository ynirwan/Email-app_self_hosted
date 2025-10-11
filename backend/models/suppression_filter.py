# backend/utils/suppression_filter.py
from typing import List, Dict, Any, Tuple, Optional
from database import get_suppressions_collection
from database_sync import get_sync_suppressions_collection  # For sync operations
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

async def filter_suppressed_subscribers(subscribers: List[Dict], target_lists: List[str] = None) -> Tuple[List[Dict], List[Dict]]:
    """
    Filter out suppressed subscribers from a list (integrates with your subscriber structure)
    Returns: (allowed_subscribers, suppressed_subscribers)
    """
    if not subscribers:
        return [], []
    
    allowed_subscribers = []
    suppressed_subscribers = []
    
    # Extract emails for batch checking
    emails = [sub.get('email', '').lower() for sub in subscribers if sub.get('email')]
    
    if not emails:
        return subscribers, []
    
    try:
        collection = get_suppressions_collection()
        
        # Build efficient query for batch checking
        query = {
            "email": {"$in": emails},
            "is_active": True
        }
        
        # Get all relevant suppressions in one query
        cursor = collection.find(query)
        suppressions_map = {}
        
        async for suppression in cursor:
            email = suppression["email"]
            if email not in suppressions_map:
                suppressions_map[email] = []
            suppressions_map[email].append(suppression)
        
        # Filter subscribers
        for subscriber in subscribers:
            email = subscriber.get('email', '').lower()
            if not email:
                continue
                
            is_suppressed = False
            suppression_details = None
            
            if email in suppressions_map:
                for suppression in suppressions_map[email]:
                    # Check global suppression
                    if suppression['scope'] == 'global':
                        is_suppressed = True
                        suppression_details = {
                            'reason': suppression['reason'],
                            'scope': 'global',
                            'notes': suppression.get('notes', ''),
                            'suppression_id': str(suppression['_id'])
                        }
                        break
                    
                    # Check list-specific suppression
                    elif suppression['scope'] == 'list_specific' and target_lists:
                        suppression_lists = set(suppression.get('target_lists', []))
                        target_lists_set = set(target_lists)
                        
                        if suppression_lists.intersection(target_lists_set):
                            is_suppressed = True
                            suppression_details = {
                                'reason': suppression['reason'],
                                'scope': 'list_specific',
                                'affected_lists': list(suppression_lists.intersection(target_lists_set)),
                                'notes': suppression.get('notes', ''),
                                'suppression_id': str(suppression['_id'])
                            }
                            break
            
            if is_suppressed:
                subscriber['suppression_details'] = suppression_details
                suppressed_subscribers.append(subscriber)
            else:
                allowed_subscribers.append(subscriber)
        
        logger.info(f"Filtered subscribers: {len(allowed_subscribers)} allowed, {len(suppressed_subscribers)} suppressed")
        
        return allowed_subscribers, suppressed_subscribers
        
    except Exception as e:
        logger.error(f"Error filtering suppressed subscribers: {str(e)}")
        # Fail open - return all subscribers to avoid blocking campaign
        return subscribers, []

def filter_suppressed_subscribers_sync(subscribers: List[Dict], target_lists: List[str] = None) -> Tuple[List[Dict], List[Dict]]:
    """
    Synchronous version for Celery tasks (integrates with your existing sync database functions)
    """
    if not subscribers:
        return [], []
    
    allowed_subscribers = []
    suppressed_subscribers = []
    
    # Extract emails for batch checking
    emails = [sub.get('email', '').lower() for sub in subscribers if sub.get('email')]
    
    if not emails:
        return subscribers, []
    
    try:
        collection = get_sync_suppressions_collection()
        
        # Build efficient query for batch checking
        query = {
            "email": {"$in": emails},
            "is_active": True
        }
        
        # Get all relevant suppressions in one query
        cursor = collection.find(query)
        suppressions_map = {}
        
        for suppression in cursor:
            email = suppression["email"]
            if email not in suppressions_map:
                suppressions_map[email] = []
            suppressions_map[email].append(suppression)
        
        # Filter subscribers
        for subscriber in subscribers:
            email = subscriber.get('email', '').lower()
            if not email:
                continue
                
            is_suppressed = False
            suppression_details = None
            
            if email in suppressions_map:
                for suppression in suppressions_map[email]:
                    # Check global suppression
                    if suppression['scope'] == 'global':
                        is_suppressed = True
                        suppression_details = {
                            'reason': suppression['reason'],
                            'scope': 'global',
                            'notes': suppression.get('notes', ''),
                            'suppression_id': str(suppression['_id'])
                        }
                        break
                    
                    # Check list-specific suppression
                    elif suppression['scope'] == 'list_specific' and target_lists:
                        suppression_lists = set(suppression.get('target_lists', []))
                        target_lists_set = set(target_lists)
                        
                        if suppression_lists.intersection(target_lists_set):
                            is_suppressed = True
                            suppression_details = {
                                'reason': suppression['reason'],
                                'scope': 'list_specific',
                                'affected_lists': list(suppression_lists.intersection(target_lists_set)),
                                'notes': suppression.get('notes', ''),
                                'suppression_id': str(suppression['_id'])
                            }
                            break
            
            if is_suppressed:
                subscriber['suppression_details'] = suppression_details
                suppressed_subscribers.append(subscriber)
            else:
                allowed_subscribers.append(subscriber)
        
        logger.info(f"Sync filtered subscribers: {len(allowed_subscribers)} allowed, {len(suppressed_subscribers)} suppressed")
        
        return allowed_subscribers, suppressed_subscribers
        
    except Exception as e:
        logger.error(f"Error in sync filtering suppressed subscribers: {str(e)}")
        # Fail open - return all subscribers to avoid blocking campaign
        return subscribers, []

async def bulk_suppression_check(emails: List[str], target_lists: List[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Bulk check suppressions for multiple emails (optimized for your campaign system)
    Returns: {email: {is_suppressed: bool, reason: str, scope: str, ...}}
    """
    if not emails:
        return {}
    
    results = {}
    normalized_emails = [email.lower() for email in emails]
    
    try:
        collection = get_suppressions_collection()
        
        # Query for all relevant suppressions
        query = {
            "email": {"$in": normalized_emails},
            "is_active": True
        }
        
        cursor = collection.find(query)
        suppressions_by_email = {}
        
        async for suppression in cursor:
            email = suppression["email"]
            if email not in suppressions_by_email:
                suppressions_by_email[email] = []
            suppressions_by_email[email].append(suppression)
        
        # Process results for each email
        for original_email in emails:
            email_lower = original_email.lower()
            
            if email_lower in suppressions_by_email:
                # Check for global suppression first (highest priority)
                global_suppression = None
                list_suppression = None
                
                for suppression in suppressions_by_email[email_lower]:
                    if suppression['scope'] == 'global':
                        global_suppression = suppression
                        break
                    elif suppression['scope'] == 'list_specific' and target_lists:
                        suppression_lists = set(suppression.get('target_lists', []))
                        if suppression_lists.intersection(set(target_lists)):
                            list_suppression = suppression
                
                # Use global suppression if exists, otherwise list-specific
                active_suppression = global_suppression or list_suppression
                
                if active_suppression:
                    results[original_email] = {
                        "is_suppressed": True,
                        "reason": active_suppression['reason'],
                        "scope": active_suppression['scope'],
                        "suppression_id": str(active_suppression['_id']),
                        "notes": active_suppression.get('notes', ''),
                        "created_at": active_suppression.get('created_at'),
                        "affected_lists": (
                            list(set(active_suppression.get('target_lists', [])).intersection(set(target_lists)))
                            if active_suppression['scope'] == 'list_specific' and target_lists
                            else []
                        )
                    }
                else:
                    results[original_email] = {"is_suppressed": False}
            else:
                results[original_email] = {"is_suppressed": False}
        
        return results
        
    except Exception as e:
        logger.error(f"Error in bulk suppression check: {str(e)}")
        # Fail open
        return {email: {"is_suppressed": False} for email in emails}

def bulk_suppression_check_sync(emails: List[str], target_lists: List[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Synchronous version for Celery tasks
    """
    if not emails:
        return {}
    
    results = {}
    normalized_emails = [email.lower() for email in emails]
    
    try:
        collection = get_sync_suppressions_collection()
        
        # Query for all relevant suppressions
        query = {
            "email": {"$in": normalized_emails},
            "is_active": True
        }
        
        cursor = collection.find(query)
        suppressions_by_email = {}
        
        for suppression in cursor:
            email = suppression["email"]
            if email not in suppressions_by_email:
                suppressions_by_email[email] = []
            suppressions_by_email[email].append(suppression)
        
        # Process results for each email
        for original_email in emails:
            email_lower = original_email.lower()
            
            if email_lower in suppressions_by_email:
                # Check for global suppression first (highest priority)
                global_suppression = None
                list_suppression = None
                
                for suppression in suppressions_by_email[email_lower]:
                    if suppression['scope'] == 'global':
                        global_suppression = suppression
                        break
                    elif suppression['scope'] == 'list_specific' and target_lists:
                        suppression_lists = set(suppression.get('target_lists', []))
                        if suppression_lists.intersection(set(target_lists)):
                            list_suppression = suppression
                
                # Use global suppression if exists, otherwise list-specific
                active_suppression = global_suppression or list_suppression
                
                if active_suppression:
                    results[original_email] = {
                        "is_suppressed": True,
                        "reason": active_suppression['reason'],
                        "scope": active_suppression['scope'],
                        "suppression_id": str(active_suppression['_id']),
                        "notes": active_suppression.get('notes', ''),
                        "created_at": active_suppression.get('created_at'),
                        "affected_lists": (
                            list(set(active_suppression.get('target_lists', [])).intersection(set(target_lists)))
                            if active_suppression['scope'] == 'list_specific' and target_lists
                            else []
                        )
                    }
                else:
                    results[original_email] = {"is_suppressed": False}
            else:
                results[original_email] = {"is_suppressed": False}
        
        return results
        
    except Exception as e:
        logger.error(f"Error in sync bulk suppression check: {str(e)}")
        # Fail open
        return {email: {"is_suppressed": False} for email in emails}

async def create_suppression_from_bounce(email: str, bounce_type: str, campaign_id: str = None, metadata: Dict = None) -> bool:
    """
    Create suppression from bounce data (integrates with your email webhook system)
    """
    try:
        collection = get_suppressions_collection()
        
        # Check if suppression already exists
        existing = await collection.find_one({"email": email.lower(), "is_active": True})
        if existing:
            logger.info(f"Suppression already exists for {email}")
            return False
        
        # Determine reason based on bounce type
        if bounce_type.lower() in ['hard', 'permanent', 'suppress']:
            reason = "bounce_hard"
        else:
            reason = "bounce_soft"
        
        suppression_doc = {
            "email": email.lower(),
            "reason": reason,
            "scope": "global",
            "target_lists": [],
            "notes": f"Auto-created from {bounce_type} bounce",
            "source": "webhook",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": "system_bounce",
            "metadata": {
                "bounce_type": bounce_type,
                "campaign_id": campaign_id,
                "webhook_data": metadata or {}
            }
        }
        
        if campaign_id:
            from bson import ObjectId
            if ObjectId.is_valid(campaign_id):
                suppression_doc["campaign_id"] = ObjectId(campaign_id)
        
        result = await collection.insert_one(suppression_doc)
        
        # Update subscriber status
        await update_subscriber_status_on_suppression(email, reason)
        
        logger.info(f"Created suppression for {email} due to {bounce_type} bounce")
        return True
        
    except Exception as e:
        logger.error(f"Error creating suppression from bounce for {email}: {str(e)}")
        return False

async def create_suppression_from_complaint(email: str, campaign_id: str = None, metadata: Dict = None) -> bool:
    """
    Create suppression from complaint data (integrates with your email webhook system)
    """
    try:
        collection = get_suppressions_collection()
        
        # Check if suppression already exists
        existing = await collection.find_one({"email": email.lower(), "is_active": True})
        if existing:
            logger.info(f"Suppression already exists for {email}")
            return False
        
        suppression_doc = {
            "email": email.lower(),
            "reason": "complaint",
            "scope": "global",
            "target_lists": [],
            "notes": "Auto-created from spam complaint",
            "source": "webhook",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": "system_complaint",
            "metadata": {
                "campaign_id": campaign_id,
                "webhook_data": metadata or {}
            }
        }
        
        if campaign_id:
            from bson import ObjectId
            if ObjectId.is_valid(campaign_id):
                suppression_doc["campaign_id"] = ObjectId(campaign_id)
        
        result = await collection.insert_one(suppression_doc)
        
        # Update subscriber status
        await update_subscriber_status_on_suppression(email, "complaint")
        
        logger.info(f"Created suppression for {email} due to spam complaint")
        return True
        
    except Exception as e:
        logger.error(f"Error creating suppression from complaint for {email}: {str(e)}")
        return False

async def update_subscriber_status_on_suppression(email: str, suppression_reason: str):
    """
    Update subscriber status when suppression is created (integrates with your subscriber system)
    """
    try:
        from database import get_subscribers_collection
        
        subscribers_collection = get_subscribers_collection()
        
        # Determine new subscriber status
        if suppression_reason in ["complaint"]:
            new_status = "complained"
        elif suppression_reason in ["bounce_hard", "bounce_soft"]:
            new_status = "bounced"
        else:
            new_status = "unsubscribed"
        
        # Update all subscribers with this email
        await subscribers_collection.update_many(
            {"email": email.lower()},
            {
                "$set": {
                    "status": new_status,
                    "updated_at": datetime.utcnow(),
                    "suppression_reason": suppression_reason,
                    "suppressed_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Updated subscriber status to {new_status} for {email}")
        
    except Exception as e:
        logger.error(f"Error updating subscriber status for {email}: {str(e)}")

# Integration helper for your existing campaign system
def get_allowed_subscribers_for_campaign(subscribers: List[Dict], target_lists: List[str]) -> List[Dict]:
    """
    Synchronous helper to get allowed subscribers for campaign sending
    (Use this in your existing Celery tasks)
    """
    allowed_subscribers, suppressed_subscribers = filter_suppressed_subscribers_sync(subscribers, target_lists)
    
    if suppressed_subscribers:
        suppressed_emails = [sub.get('email') for sub in suppressed_subscribers]
        logger.info(f"Filtered out {len(suppressed_subscribers)} suppressed subscribers: {suppressed_emails[:10]}...")
    
    return allowed_subscribers

# Quick suppression check for single email (for your email sending tasks)
def is_email_suppressed_quick(email: str, target_lists: List[str] = None) -> bool:
    """
    Quick synchronous check if email is suppressed (for use in Celery tasks)
    """
    try:
        collection = get_sync_suppressions_collection()
        
        # Check global suppression first
        global_suppression = collection.find_one({
            "email": email.lower(),
            "is_active": True,
            "scope": "global"
        })
        
        if global_suppression:
            return True
        
        # Check list-specific suppression if target lists provided
        if target_lists:
            list_suppression = collection.find_one({
                "email": email.lower(),
                "is_active": True,
                "scope": "list_specific",
                "target_lists": {"$in": target_lists}
            })
            
            if list_suppression:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking suppression for {email}: {str(e)}")
        return False  # Fail open

