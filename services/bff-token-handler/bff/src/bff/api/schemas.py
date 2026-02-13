from typing import Literal
from pydantic import BaseModel


class CommonBffProxyResponse(BaseModel):
    bff_status: Literal["Proxy Success", "Proxy Error"]
    upstream: dict
