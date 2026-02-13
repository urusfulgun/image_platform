from pydantic import BaseModel

class UserSession(BaseModel):
    access_token: str
    refresh_token: str
    kid: str  # References the key in the Registry