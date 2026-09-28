from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.system import SystemInfo

router = APIRouter()


@router.get("/system/info", response_model=SystemInfo)
async def system_info(
    settings: Settings = Depends(get_settings),
    current_user: CurrentUser = Depends(get_current_user),
) -> SystemInfo:
    return SystemInfo(
        name=settings.app_name,
        environment=settings.app_env,
        version="0.1.0",
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
    )


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready"}
