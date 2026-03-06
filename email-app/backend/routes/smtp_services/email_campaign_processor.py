# backend/routes/smtp_services/sync_email_campaign_processor.py
from typing import Optional, Dict, Any, List
from datetime import datetime
from jinja2 import Environment, BaseLoader
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

class SyncEmailCampaignProcessor:
    """Synchronous version of EmailCampaignProcessor for Celery tasks"""
    
    def __init__(
        self,
        campaigns_collection,
        templates_collection,
        subscribers_collection,
    ):
        self.campaigns_collection = campaigns_collection
        self.templates_collection = templates_collection
        self.subscribers_collection = subscribers_collection
        self.jinja_env = Environment(loader=BaseLoader())

    def get_campaign_data(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Fetch campaign data from MongoDB including template info synchronously"""
        
        if not ObjectId.is_valid(campaign_id):
            logger.error(f"Invalid campaign ID: {campaign_id}")
            return None

        campaign = self.campaigns_collection.find_one({'_id': ObjectId(campaign_id)})
        if not campaign:
            logger.error(f"Campaign not found: {campaign_id}")
            return None

        template_id = campaign.get('template_id')
        if not template_id or not ObjectId.is_valid(template_id):
            logger.error(f"Template ID invalid or missing for campaign {campaign_id}")
            return None

        template = self.templates_collection.find_one({'_id': ObjectId(template_id)})
        if not template:
            logger.error(f"Template not found for campaign {campaign_id}")
            return None

        campaign['template'] = template
        return campaign

    def get_subscribers_for_campaign(
        self,
        campaign: Dict[str, Any],
        batch_size: int = 1000,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Get subscribers for campaign in batches synchronously"""
        target_lists = campaign.get('target_lists', [])
        if not target_lists:
            return []

        query = {
            'list': {'$in': target_lists},
            'status': 'active'
        }
        cursor = self.subscribers_collection.find(query).skip(skip).limit(batch_size)
        return list(cursor)

    def render_content(self, template_content: str, subscriber_data: Dict[str, Any]) -> str:
        """Render dynamic content using Jinja2 templates"""
        try:
            template = self.jinja_env.from_string(template_content)
            return template.render(**subscriber_data)
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            return template_content

    def prepare_email_content(
        self,
        campaign: Dict[str, Any],
        subscriber: Dict[str, Any]
    ) -> Dict[str, str]:
        """Prepare personalized email content for a subscriber"""
        try:
            subscriber_data = {
                'email': subscriber.get('email', ''),
                **subscriber.get('standard_fields', {}),
                **subscriber.get('custom_fields', {})
            }

            field_map = campaign.get('field_map', {})
            fallback_values = campaign.get('fallback_values', {})
            mapped_data = {}

            for template_field, subscriber_field in field_map.items():
                value = subscriber_data.get(subscriber_field)
                if value is None and template_field in fallback_values:
                    value = fallback_values[template_field]
                mapped_data[template_field] = value or ''

            for key, value in subscriber_data.items():
                if key not in mapped_data:
                    mapped_data[key] = value

            template = campaign['template']
            html_content = self._extract_html_from_template(template['content_json'])
            rendered_html = self.render_content(html_content, mapped_data)
            rendered_subject = self.render_content(campaign['subject'], mapped_data)

            return {
                'html_content': rendered_html,
                'subject': rendered_subject,
                'recipient_email': subscriber['email']
            }
        except Exception as e:
            logger.error(f"Error preparing email content: {e}")
            return {}

    def _extract_html_from_template(self, content_json: Dict[str, Any]) -> str:
        """Extract basic HTML content from template JSON structure"""
        try:
            body = content_json.get('body', {})
            rows = body.get('rows', [])
            html_parts = ['<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>']
            for row in rows:
                columns = row.get('columns', [])
                html_parts.append('<div class="row">')
                for column in columns:
                    contents = column.get('contents', [])
                    html_parts.append('<div class="column">')
                    for content in contents:
                        content_type = content.get('type', '')
                        if content_type == 'text':
                            text = content.get('values', {}).get('text', '')
                            html_parts.append(f'<div>{text}</div>')
                        elif content_type == 'image':
                            src = content.get('values', {}).get('src', '')
                            alt = content.get('values', {}).get('alt', '')
                            html_parts.append(f'<img src="{src}" alt="{alt}" />')
                    html_parts.append('</div>')
                html_parts.append('</div>')
            html_parts.append('</body></html>')
            return ''.join(html_parts)
        except Exception as e:
            logger.error(f"Error extracting HTML from template: {e}")
            return "<html><body>Error rendering template</body></html>"
