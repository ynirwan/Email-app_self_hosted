from fastapi import APIRouter, HTTPException, Response
from typing import List, Dict, Any, Optional
from bson import ObjectId
from database import get_templates_collection
from models.campaign_model import TemplateCreate, TemplateOut
import re
import json
from datetime import datetime

router = APIRouter(tags=["templates"])

class TemplateRenderer:
    """Handles rendering of different template types"""
    
    @staticmethod
    def extract_fields_from_content(content: str) -> List[str]:
        """Extract placeholder fields from content"""
        if not content:
            return []
        
        # Find all {{field_name}} patterns
        pattern = r'\{\{([^}]+)\}\}'
        matches = re.findall(pattern, content)
        return [m.strip() for m in matches]
    
    @staticmethod
    def render_drag_drop_template(blocks: List[Dict], fields_data: Dict = None) -> str:
        """Render drag-drop template blocks to HTML"""
        if not blocks:
            return ""
        
        html_parts = []
        html_parts.append('''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Template</title>
            <style>
                body { margin: 0; padding: 20px; font-family: Arial, sans-serif; }
                .email-container { max-width: 600px; margin: 0 auto; }
                .block { margin-bottom: 20px; }
                .text-block { line-height: 1.6; }
                .button-block { text-align: center; margin: 20px 0; }
                .button { display: inline-block; padding: 12px 24px; text-decoration: none; border-radius: 4px; }
                .image-block { text-align: center; }
                .image-block img { max-width: 100%; height: auto; }
                .divider { border-top: 1px solid #ddd; margin: 20px 0; }
                .spacer { height: 20px; }
            </style>
        </head>
        <body>
            <div class="email-container">
        ''')
        
        # Sort blocks by position
        sorted_blocks = sorted(blocks, key=lambda x: x.get('position', 0))
        
        for block in sorted_blocks:
            block_type = block.get('type', 'text')
            content = block.get('content', '')
            styles = block.get('styles', {})
            
            # Replace placeholders with actual data
            if fields_data:
                for field, value in fields_data.items():
                    content = content.replace(f'{{{{{field}}}}}', str(value))
            
            # Generate CSS from styles
            style_str = ""
            if styles:
                style_parts = []
                for key, value in styles.items():
                    css_key = key.replace('_', '-')
                    style_parts.append(f"{css_key}: {value}")
                if style_parts:
                    style_str = f' style="{"; ".join(style_parts)}"'
            
            if block_type == 'text':
                html_parts.append(f'<div class="block text-block"{style_str}>{content}</div>')
            elif block_type == 'button':
                html_parts.append(f'<div class="block button-block"{style_str}><a href="#" class="button">{content}</a></div>')
            elif block_type == 'image':
                html_parts.append(f'<div class="block image-block"{style_str}><img src="{content}" alt="Image" /></div>')
            elif block_type == 'divider':
                html_parts.append(f'<div class="block divider"{style_str}></div>')
            elif block_type == 'spacer':
                height = styles.get('height', '20px')
                html_parts.append(f'<div class="block spacer" style="height: {height}"></div>')
            else:
                # Custom block type
                html_parts.append(f'<div class="block"{style_str}>{content}</div>')
        
        html_parts.append('''
            </div>
        </body>
        </html>
        ''')
        
        return ''.join(html_parts)
    
    @staticmethod
    def render_html_template(html_content: str, fields_data: Dict = None) -> str:
        """Render HTML template with field replacements"""
        if not html_content:
            return ""
        
        rendered_html = html_content
        
        # Replace placeholders with actual data
        if fields_data:
            for field, value in fields_data.items():
                rendered_html = rendered_html.replace(f'{{{{{field}}}}}', str(value))
        
        return rendered_html

@router.post("/", response_model=TemplateOut)
async def create_template(template: TemplateCreate):
    """Create a new template"""
    col = get_templates_collection()
    doc = template.dict()
    
    # Add metadata
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    
    # Extract fields based on template mode
    content_json = doc.get("content_json", {})
    mode = content_json.get("mode", "html")
    fields = []
    
    if mode == "drag-drop":
        blocks = content_json.get("blocks", [])
        for block in blocks:
            block_content = block.get("content", "")
            block_fields = TemplateRenderer.extract_fields_from_content(block_content)
            fields.extend(block_fields)
    elif mode == "html":
        html_content = content_json.get("content", "")
        fields = TemplateRenderer.extract_fields_from_content(html_content)
    
    doc["fields"] = [f.strip() for f in list(set(fields))]  # ✅ Strip spaces from each field
    
    result = await col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@router.get("/", response_model=List[TemplateOut])
async def list_templates(mode: Optional[str] = None):
    """List all templates, optionally filtered by mode"""
    col = get_templates_collection()
    templates = []
    
    # Build query
    query = {}
    if mode:
        query["content_json.mode"] = mode
    
    cursor = col.find(query).sort("created_at", -1)
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        templates.append(doc)
    return templates

@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: str):
    """Get a specific template"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    
    doc["_id"] = str(doc["_id"])
    return doc

@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(template_id: str, template: TemplateCreate):
    """Update a template"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    doc = template.dict()
    doc["updated_at"] = datetime.utcnow()
    
    # Re-extract fields
    content_json = doc.get("content_json", {})
    mode = content_json.get("mode", "html")
    fields = []
    
    if mode == "drag-drop":
        blocks = content_json.get("blocks", [])
        for block in blocks:
            block_content = block.get("content", "")
            block_fields = TemplateRenderer.extract_fields_from_content(block_content)
            fields.extend(block_fields)
    elif mode == "html":
        html_content = content_json.get("content", "")
        fields = TemplateRenderer.extract_fields_from_content(html_content)
    
    doc["fields"] = [f.strip() for f in list(set(fields))]  # ✅ Strip spaces from each field
    
    result = await col.update_one(
        {"_id": ObjectId(template_id)}, 
        {"$set": doc}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Return updated template
    updated_doc = await col.find_one({"_id": ObjectId(template_id)})
    updated_doc["_id"] = str(updated_doc["_id"])
    return updated_doc

@router.delete("/{template_id}")
async def delete_template(template_id: str):
    """Delete a template"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    result = await col.delete_one({"_id": ObjectId(template_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {"message": "Template deleted successfully"}

@router.get("/{template_id}/fields", response_model=List[str])
async def get_template_fields(template_id: str):
    """Get template fields for personalization"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return doc.get("fields", [])

@router.post("/{template_id}/render")
async def render_template(template_id: str, fields_data: Dict[str, Any] = None):
    """Render template to HTML with optional field data"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    
    content_json = doc.get("content_json", {})
    mode = content_json.get("mode", "html")
    
    try:
        if mode == "drag-drop":
            blocks = content_json.get("blocks", [])
            html = TemplateRenderer.render_drag_drop_template(blocks, fields_data or {})
        elif mode == "html":
            html_content = content_json.get("content", "")
            html = TemplateRenderer.render_html_template(html_content, fields_data or {})
        else:
            # Handle other modes or fallback
            html = "<p>Template mode not supported for rendering</p>"
        
        return {"html": html, "mode": mode}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rendering template: {str(e)}")

@router.get("/{template_id}/preview")
async def preview_template(template_id: str):
    """Get template preview HTML"""
    return await render_template(template_id)

@router.post("/{template_id}/duplicate")
async def duplicate_template(template_id: str):
    """Duplicate an existing template"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Remove _id and modify name
    del doc["_id"]
    doc["name"] = f"{doc['name']} (Copy)"
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    
    result = await col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@router.post("/convert/{template_id}")
async def convert_template_mode(template_id: str, target_mode: str):
    """Convert template from one mode to another"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    if target_mode not in ["html", "drag-drop", "visual"]:
        raise HTTPException(status_code=400, detail="Invalid target mode")
    
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    
    content_json = doc.get("content_json", {})
    current_mode = content_json.get("mode", "html")
    
    if current_mode == target_mode:
        return {"message": "Template is already in the target mode"}
    
    # Convert based on modes
    if current_mode == "html" and target_mode == "drag-drop":
        # Convert HTML to drag-drop blocks
        html_content = content_json.get("content", "")
        blocks = [{
            "id": int(datetime.utcnow().timestamp() * 1000),
            "type": "text",
            "content": html_content,
            "styles": {},
            "position": 0
        }]
        content_json = {
            "mode": "drag-drop",
            "blocks": blocks
        }
    elif current_mode == "drag-drop" and target_mode == "html":
        # Convert drag-drop to HTML
        blocks = content_json.get("blocks", [])
        html_content = TemplateRenderer.render_drag_drop_template(blocks)
        content_json = {
            "mode": "html",
            "content": html_content
        }
    else:
        raise HTTPException(status_code=400, detail=f"Conversion from {current_mode} to {target_mode} not supported")
    
    # Update template
    update_doc = {
        "content_json": content_json,
        "updated_at": datetime.utcnow()
    }
    
    await col.update_one(
        {"_id": ObjectId(template_id)}, 
        {"$set": update_doc}
    )
    
    return {"message": f"Template converted from {current_mode} to {target_mode}"}

@router.get("/{template_id}/export")
async def export_template(template_id: str, format: str = "json"):
    """Export template in specified format"""
    col = get_templates_collection()
    
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Remove MongoDB _id for export
    doc["_id"] = str(doc["_id"])
    
    if format == "json":
        return Response(
            content=json.dumps(doc, default=str, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={doc['name']}.json"}
        )
    elif format == "html":
        # Render and export as HTML
        render_result = await render_template(template_id)
        return Response(
            content=render_result["html"],
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename={doc['name']}.html"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid export format")

