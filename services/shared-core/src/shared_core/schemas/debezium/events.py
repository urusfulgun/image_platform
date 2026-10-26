from typing import Optional
from pydantic import BaseModel, Field


class KeycloakUserEvent(BaseModel):
    # Standard Keycloak user_entity columns
    # Map 'id' from Postgres/Kafka to 'sub' in Python
    sub: str = Field(..., alias="id")
    username: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    enabled: bool = True
    
    # Metadata added by the Debezium 'unwrap' transform
    op: str = Field(..., alias="__op") # 'c'=create, 'u'=update, 'd'=delete
    deleted: bool = Field(False, alias="__deleted")  # "true"/"false" string from rewrite mode

    class Config:
        populate_by_name = True
