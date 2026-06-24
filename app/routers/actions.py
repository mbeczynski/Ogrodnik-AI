import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import select

from ..config import settings
from ..db import get_session
from ..models import GardenAction

router = APIRouter(prefix="/actions", tags=["actions"])

ALLOWED_ACTION_TYPES = {"fertilizing", "planting", "pruning", "pest_control", "watering_manual", "other"}


@router.post("")
async def create_action(
    action_type: str = Form(...),
    description: str = Form(""),
    product: str = Form(""),
    amount: str = Form(""),
    zone: str = Form(""),
    photo: Optional[UploadFile] = None,
):
    photo_path = None
    if photo is not None and photo.filename:
        suffix = Path(photo.filename).suffix or ".jpg"
        filename = f"{uuid.uuid4().hex}{suffix}"
        dest = settings.photos_dir / filename
        dest.write_bytes(await photo.read())
        photo_path = str(dest.relative_to(settings.data_dir))

    action_type = action_type if action_type in ALLOWED_ACTION_TYPES else "other"

    with get_session() as session:
        action = GardenAction(
            timestamp=datetime.utcnow(),
            action_type=action_type,
            description=description or None,
            product=product or None,
            amount=amount or None,
            zone=zone or None,
            photo_path=photo_path,
        )
        session.add(action)
        session.commit()

    return RedirectResponse(url="/", status_code=303)


@router.get("")
def list_actions() -> list[GardenAction]:
    with get_session() as session:
        return session.exec(select(GardenAction).order_by(GardenAction.timestamp.desc())).all()
