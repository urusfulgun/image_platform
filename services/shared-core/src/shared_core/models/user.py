"""User Pydantic schema."""
import uuid
from datetime import datetime
import pydantic


class UserSchema(pydantic.BaseModel):
    """Shadow user representation synced from KeyCloak."""

    id: uuid.UUID
    kc_sub: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}
