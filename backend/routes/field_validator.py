# utils/field_validator.py
import logging
from typing import Dict, List, Any
from .field_handler import FIELD_TIERS

logger = logging.getLogger(__name__)

async def analyze_list_fields(list_id: str) -> dict:
    """Analyze field availability and population rates for a list"""
    # This is a placeholder - you'll need to implement based on your subscriber structure
    # For now, return a basic structure
    
    # TODO: Replace this with actual analysis of your subscriber data
    # You would query your subscribers collection and analyze field population
    
    return {
        "tiers": {
            "universal": {
                "email": {"population_rate": 1.0}
            },
            "standard": {
                "first_name": {"population_rate": 0.8},
                "last_name": {"population_rate": 0.8},
                "phone": {"population_rate": 0.6},
                "company": {"population_rate": 0.7},
                "country": {"population_rate": 0.5},
                "city": {"population_rate": 0.5},
                "job_title": {"population_rate": 0.4}
            },
            "custom": {}  # Will be populated dynamically based on actual data
        }
    }

async def validate_tiered_field_mapping(field_map: Dict[str, str], target_lists: List[str]) -> Dict:
    """Validate field mappings against three-tier system"""
    
    validated_mapping = {}
    mapping_strategy = {}
    field_availability = {}
    
    # Get field analysis for all target lists
    for list_id in target_lists:
        analysis = await analyze_list_fields(list_id)
        field_availability[list_id] = analysis["tiers"]
    
    for template_field, mapping in field_map.items():
        if not mapping or mapping in ["__EMPTY__", "__DEFAULT__"]:
            validated_mapping[template_field] = mapping
            mapping_strategy[template_field] = {
                "type": "fallback",
                "action": mapping
            }
            continue
        
        # Parse tier-based mapping (e.g., "standard.first_name" or "custom.membership_level")
        if "." in mapping:
            tier, field_name = mapping.split(".", 1)
            
            # Validate tier exists
            if tier not in ["universal", "standard", "custom"]:
                raise ValueError(f"Invalid tier '{tier}' in mapping '{mapping}'. Valid tiers: universal, standard, custom")
            
            # Validate field exists in target lists
            availability_rates = []
            for list_id in target_lists:
                list_fields = field_availability.get(list_id, {}).get(tier, {})
                if field_name in list_fields:
                    availability_rates.append(list_fields[field_name]["population_rate"])
                else:
                    availability_rates.append(0.0)
            
            avg_availability = sum(availability_rates) / len(availability_rates) if availability_rates else 0.0
            
            validated_mapping[template_field] = mapping
            mapping_strategy[template_field] = {
                "type": "tiered_field",
                "tier": tier,
                "field_name": field_name,
                "average_availability": avg_availability,
                "per_list_availability": dict(zip(target_lists, availability_rates))
            }
            
            # Warn about low availability
            if avg_availability < 0.5:
                logger.warning(f"Field {template_field} mapped to {mapping} has low availability: {avg_availability:.1%}")
        
        else:
            # Legacy mapping or error
            logger.warning(f"Legacy field mapping format detected: {mapping}. Consider using tier.field_name format")
            validated_mapping[template_field] = mapping
            mapping_strategy[template_field] = {
                "type": "legacy_field",
                "field_name": mapping,
                "average_availability": 0.5  # Assume 50% for legacy fields
            }
    
    return {
        "field_map": validated_mapping,
        "strategy": mapping_strategy,
        "summary": {
            "total_fields": len(field_map),
            "tiered_mappings": len([s for s in mapping_strategy.values() if s["type"] == "tiered_field"]),
            "fallback_mappings": len([s for s in mapping_strategy.values() if s["type"] == "fallback"]),
            "legacy_mappings": len([s for s in mapping_strategy.values() if s["type"] == "legacy_field"])
        }
    }

async def calculate_tiered_audience_count(target_lists: List[str], validated_mapping: dict) -> int:
    """Calculate target audience count with tier-aware logic"""
    # For now, use your existing compute_target_list_count function
    # This is a placeholder for more sophisticated counting logic
    from routes.list_validator import compute_target_list_count
    return await compute_target_list_count(target_lists)

