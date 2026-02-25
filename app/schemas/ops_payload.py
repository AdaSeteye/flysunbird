from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional

class PublicRouteOut(BaseModel):
    """One route as returned by GET /api/v1/public/routes."""
    id: str
    from_: str = Field(alias="from", description="Origin label, e.g. Dar es Salaam Airport")
    to: str
    region: str
    mainRegion: str = "MAINLAND"
    subRegion: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

class OpsSlot(BaseModel):
    start: str
    end: str
    priceUSD: int
    seatsAvailable: int
    flightNo: str = "FSB"
    cabin: str = "Economy"

class OpsPayload(BaseModel):
    from_: str
    to: str
    region: str = "Tanzania"
    currency: str = "USD"
    dateStr: str
    slots: List[OpsSlot]

    class Config:
        populate_by_name = True
        fields = {"from_": "from"}
