from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.security_admin import verify_admin
from app.services.client_prompts import list_prompts_for_client, upsert_prompt_for_client

router = APIRouter(prefix="/admin/client", tags=["admin:client_prompts"])

class PromptUpdate(BaseModel):
    value: str = Field(..., min_length=1, max_length=5000)

@router.get("/{client_id}/prompts", dependencies=[Depends(verify_admin)])
async def get_client_prompts(client_id: int):
    data = await list_prompts_for_client(client_id)
    return [{"key": k, "value": v} for k, v in sorted(data.items())]

@router.put("/{client_id}/prompts/{key}", dependencies=[Depends(verify_admin)])
async def put_client_prompt(client_id: int, key: str, body: PromptUpdate):
    try:
        saved = await upsert_prompt_for_client(client_id, key, body.value)
        return {"ok": True, "key": saved}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/_debug")
async def _client_prompts_debug():
    return {"ok": True, "router": "admin_client_prompts"}
