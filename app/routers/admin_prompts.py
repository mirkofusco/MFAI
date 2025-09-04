from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.prompts import PromptUpdate
from app.services.prompts import list_prompts, upsert_prompt
from app.database import get_db
from app.security_admin import verify_admin

router = APIRouter(prefix="/admin/prompts", tags=["admin:prompts"])

@router.get("", dependencies=[Depends(verify_admin)])
def get_prompts(db: Session = Depends(get_db)):
    data = list_prompts(db)
    return [{"key": k, "value": v} for k, v in sorted(data.items())]

@router.put("/{key}", dependencies=[Depends(verify_admin)])
def put_prompt(key: str, body: PromptUpdate, db: Session = Depends(get_db)):
    try:
        saved_key = upsert_prompt(db, key, body.value)
        return {"ok": True, "key": saved_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
