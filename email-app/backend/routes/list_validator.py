# Step 2: Helper function to compute target_list_count automatically
from database import get_subscribers_collection
from typing import List, Optional, Dict, Any  # ✅ Make sure List is imported
import logging

logger = logging.getLogger(__name__)

async def compute_target_list_count(target_lists: List[str]) -> int:
    try:
        if not target_lists:
            return 0
        
        subscribers_collection = get_subscribers_collection()
        total_count = 0
        
        # Get count from each target list
        for list_id in target_lists:
            try:
                # Count subscribers in this specific list
                count = await subscribers_collection.count_documents({"list": list_id})
                total_count += count
                logger.info(f"List '{list}' has {count} subscribers")
                
            except Exception as e:
                logger.warning(f"Failed to count subscribers in list '{list}': {e}")
                # Continue with other lists even if one fails
                continue
        
        logger.info(f"Total computed count across {len(target_lists)} lists: {total_count}")
        return total_count
        
    except Exception as e:
        logger.error(f"Failed to compute target list count: {e}")
        # Return 0 as fallback - better than crashing
        return 0



async def validate_target_lists_exist(target_lists: List[str]) -> bool:
    """
    Validate that all target lists actually exist in the database.
    """
    try:
        if not target_lists:
            return False
        
        # ✅ DEBUGGING: Log what we're actually receiving
        logger.info(f"🔍 Validating target_lists type: {type(target_lists)}")
        logger.info(f"🔍 Validating target_lists value: {target_lists}")
        
        # ✅ Ensure target_lists is a list of strings
        if isinstance(target_lists, str):
            target_lists = [target_lists]
        elif not isinstance(target_lists, list):
            logger.error(f"❌ Invalid target_lists type: {type(target_lists)}")
            return False
        
        subscribers_collection = get_subscribers_collection()
        
        for list_id in target_lists:
            # ✅ Ensure each list_id is a string
            if not isinstance(list_id, str):
                logger.warning(f"❌ Invalid list_id type: {type(list_id)}, value: {list_id}")
                continue
                
            # ✅ Use "list" field (not "list_id") as we discovered earlier
            exists = await subscribers_collection.find_one({"list": list_id})
            if not exists:
                logger.warning(f"❌ Target list '{list_id}' does not exist or has no subscribers")
                # Show available lists for debugging
                all_lists = await subscribers_collection.distinct("list")
                logger.info(f"💡 Available lists in database: {all_lists}")
                return False
            else:
                logger.info(f"✅ List '{list_id}' exists and has subscribers")
        
        return True
    except Exception as e:
        logger.error(f"❌ Failed to validate target lists: {e}")
        return False








