from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import Wellness
from ..schemas import WellnessOut
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/wellness", tags=["wellness"])


@router.get("", response_model=list[WellnessOut])
async def get_wellness(days: int = 30, db: AsyncSession = Depends(get_db)):
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = await db.execute(
        select(Wellness)
        .where(Wellness.date >= cutoff)
        .order_by(Wellness.date)
    )
    return [WellnessOut.model_validate(w) for w in result.scalars().all()]
