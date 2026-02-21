"""King County parcel ingest agent."""

from openclaw.db.models import CountyEnum
from openclaw.ingest.base import BaseIngestAgent

ENDPOINT = (
    "https://gismaps.kingcounty.gov/arcgis/rest/services/"
    "Property/KingCo_PropertyInfo/MapServer/2/query"
)

FIELD_MAP = {
    "PIN": "parcel_id",
    "ADDR_FULL": "address",
    "LOTSQFT": "lot_sf",
    "PREUSE_DESC": "present_use",
    "KCA_ZONING": "zone_code",
    "APPRLNDVAL": "assessed_value",
    # No owner_name in this layer — would need separate assessor lookup
}


class KingCountyAgent(BaseIngestAgent):
    county = CountyEnum.king
    endpoint = ENDPOINT
    field_map = FIELD_MAP

    @property
    def out_fields(self) -> str:
        return ",".join(FIELD_MAP.keys())


if __name__ == "__main__":
    import asyncio
    agent = KingCountyAgent()
    result = asyncio.run(agent.run())
    print(result)
