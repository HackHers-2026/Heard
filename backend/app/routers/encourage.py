from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.dependencies import get_current_user
from app.services import gemini

router = APIRouter(prefix="/api", tags=["encourage"])


class EncourageRequest(BaseModel):
    mode: str = "quick"
    context: Optional[str] = None


@router.post("/encourage")
def encourage_handler(body: EncourageRequest, user=Depends(get_current_user)):
    return gemini.encourage(body.mode, body.context)
