"""Pre-training: domain-specific coaching the AI gives before a practice run."""
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models import Domain, User
from app.schemas import PreTrainingResponse
from app.services import gemini

router = APIRouter(prefix="/training", tags=["training"])


@router.get("/pre/{domain}", response_model=PreTrainingResponse)
async def pre_training(domain: Domain, current: User = Depends(get_current_user)):
    result = await gemini.pre_training(domain.value)
    return PreTrainingResponse(
        domain=domain,
        coaching=result["coaching"],
        checklist=result.get("checklist", []),
    )
