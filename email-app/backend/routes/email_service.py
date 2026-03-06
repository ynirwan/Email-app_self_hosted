# app/services/email_service.py (Updated)
import asyncio
from .rate_limiter import rate_limiter

class EmailService:
    # ... existing code ...
    
    async def submit_batch_to_mta_with_limits(self, email_batch: List[Dict]) -> List[Dict]:
        """Submit batch with rate limiting"""
        results = []
        
        for email_data in email_batch:
            # Check rate limit before sending
            rate_check = await rate_limiter.check_rate_limit()
            
            if not rate_check["allowed"]:
                logging.warning(f"Rate limit exceeded: {rate_check['reason']}")
                
                # Wait until we can send again
                await asyncio.sleep(rate_check["retry_after"])
                
                # Check again after waiting
                rate_check = await rate_limiter.check_rate_limit()
                if not rate_check["allowed"]:
                    results.append({
                        "status": "rate_limited",
                        "recipient": email_data['recipient_email'],
                        "error": f"Rate limit exceeded: {rate_check['reason']}",
                        "failed_at": datetime.utcnow()
                    })
                    continue
            
            # Submit email
            result = await self.submit_email_to_mta(email_data)
            
            # Record successful submission for rate limiting
            if result["status"] == "submitted":
                await rate_limiter.record_send()
            
            results.append(result)
            
            # Small delay between emails
            await asyncio.sleep(0.5)  # Adjusted for rate limiting
        
        return results

