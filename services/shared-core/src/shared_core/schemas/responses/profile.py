from pydantic import BaseModel, EmailStr, Field


class UserProfileResponse(BaseModel):
    """
    Sanitized user information for the User Agent (Browser).
    Excludes sensitive/internal claims like 'sub', 'iss', and 'aud'.
    """
    name: str = Field(..., examples=["John Doe"])
    given_name: str = Field(..., alias="given_name")
    family_name: str = Field(..., alias="family_name")
    preferred_username: str = Field(..., alias="preferred_username")
    email: EmailStr
    email_verified: bool

    class Config:
        # Allows using the dictionary keys from Keycloak directly
        populate_by_name = True