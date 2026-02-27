from typing import Optional, Generic, TypeVar
from pydantic import BaseModel, Field

# Define a TypeVar to make the payload reusable for different tables
T = TypeVar("T")


class DebeziumSource(BaseModel):
    """Metadata about the source of the event"""

    version: str
    connector: str
    name: str
    ts_ms: int
    db: str
    schema_: str = Field(..., alias="schema")
    table: str
    txId: int | None = None
    lsn: int | None = None


class KeycloakUserPayload(BaseModel):
    """The actual columns from the public.user_entity table"""

    id: str  # This is the Keycloak UUID
    username: str | None = None
    email: str | None = None
    first_name: str | None = Field(None, alias="first_name")
    last_name: str | None = Field(None, alias="last_name")
    enabled: bool = True
    created_timestamp: Optional[int] = Field(None, alias="created_timestamp")


class DebeziumEvent(BaseModel, Generic[T]):
    """The top-level Debezium envelope"""

    before: T | None = None
    after: T | None = None
    source: DebeziumSource
    op: str  # 'c' for create, 'u' for update, 'd' for delete
    ts_ms: int


# Type alias for your specific Keycloak event
UserRegistrationEvent = DebeziumEvent[KeycloakUserPayload]


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
    deleted: Optional[str] = Field(None, alias="__deleted")

    class Config:
        populate_by_name = True
