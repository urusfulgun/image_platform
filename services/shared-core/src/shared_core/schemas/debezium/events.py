from pydantic import BaseModel, Field


class KeycloakUserEvent(BaseModel):
    # Standard Keycloak user_entity columns
    # Map 'id' from Postgres/Kafka to 'sub' in Python
    sub: str = Field(..., alias="id")
    username: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True

    # Metadata added by the Debezium 'unwrap' transform
    op: str = Field(..., alias="__op")  # 'c'=create, 'u'=update, 'd'=delete
    deleted: bool = Field(
        False, alias="__deleted"
    )  # "true"/"false" string from rewrite mode

    class Config:
        populate_by_name = True
