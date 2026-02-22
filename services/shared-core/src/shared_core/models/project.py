"""Project Pydantic schemas."""
import uuid
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel


class ProjectStatus(StrEnum):
    Created = "Created"
    Processing = "Processing"
    Completed = "Completed"


class ProjectSchema(BaseModel):
    """Project representation."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    status: ProjectStatus = ProjectStatus.Created
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateProjectRequest(BaseModel):
    name: str
