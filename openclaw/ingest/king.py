"""King County parcel ingest agent."""

from openclaw.db.models import CountyEnum
from openclaw.ingest.base import BaseIngestAgent

ENDPOINT = (
    "https://gisdata.kingcounty.gov/arcgis/rest/services/"
    "OpenDataPortal/property__kc_open_data/MapServer/205/query"
)

FIELD_MAP = {
    "PIN": "parcel_id",
    "SITUSADDR": "address",
    "SQ_FT_LOT": "lot_sf",
    "PRESENT_USE": "present_use",
    "ZONE_CODE": "zone_code",
    "APPRAISED_VALUE": "assessed_value",
    "OWNER_NAME": "owner_name",
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
