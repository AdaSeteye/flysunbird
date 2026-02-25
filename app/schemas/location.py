from pydantic import BaseModel
from typing import List, Optional

class LocationIn(BaseModel):
    region: str
    code: str
    name: str
    subs: List[str] = []
    active: bool = True

class LocationPatch(BaseModel):
    region: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    subs: Optional[List[str]] = None
    active: Optional[bool] = None
