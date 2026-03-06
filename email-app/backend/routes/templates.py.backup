from fastapi import APIRouter, HTTPException
from typing import List
from bson import ObjectId
from database import get_templates_collection
from models.campaign_model import TemplateCreate, TemplateOut

router = APIRouter(tags=["templates"])

@router.post("/", response_model=TemplateOut)
async def create_template(template: TemplateCreate):
    col = get_templates_collection()
    doc = template.dict()
    result = await col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@router.get("/", response_model=List[TemplateOut])
async def list_templates():
    col = get_templates_collection()
    templates = []
    cursor = col.find()
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        templates.append(doc)
    return templates



@router.get("/{template_id}/fields", response_model=List[str])
async def get_template_fields(template_id: str):
    col = get_templates_collection()
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    return doc.get("fields", [])



@router.put("/{id}", response_model=TemplateOut)
async def update_template(id: str, template: TemplateCreate):

    templates_collection = get_templates_collection()
    result = await templates_collection.update_one(
        {"_id": ObjectId(id)}, {"$set": template.dict()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    # Return updated template
    doc = await templates_collection.find_one({"_id": ObjectId(id)})
    doc["_id"] = str(doc["_id"])
    return doc

@router.get("/{template_id}/rendered")
async def get_template_html(template_id: str):
    col = get_templates_collection()
    doc = await col.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    # If you store the HTML:
    return {"html": doc.get("html", "")}
    # Or, if you need to render from JSON, use your render utility here




@router.delete("/{template_id}")
async def delete_templates(template_id: str):
    templates_collection = get_templates_collection()
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")

    result = await templates_collection.delete_one({"_id": ObjectId(template_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {"message": "Template deleted successfully"}

