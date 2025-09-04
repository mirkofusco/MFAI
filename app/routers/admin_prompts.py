from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.security_admin import verify_admin
from app.services.prompts import list_prompts, upsert_prompt

router = APIRouter(prefix="/admin/prompts", tags=["admin:prompts"])

class PromptUpdate(BaseModel):
    value: str = Field(..., min_length=1, max_length=5000)

@router.get("", dependencies=[Depends(verify_admin)])
async def get_prompts():
    data = await list_prompts()
    return [{"key": k, "value": v} for k, v in sorted(data.items())]

@router.put("/{key}", dependencies=[Depends(verify_admin)])
async def put_prompt(key: str, body: PromptUpdate):
    try:
        saved_key = await upsert_prompt(key, body.value)
        return {"ok": True, "key": saved_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
