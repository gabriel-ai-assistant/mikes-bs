"""Snohomish County parcel ingest agent."""

from openclaw.db.models import CountyEnum
from openclaw.ingest.base import BaseIngestAgent

ENDPOINT = (
    "https://services1.arcgis.com/ZnUys0yQhBmQzAHh/arcgis/rest/services/"
    "Assessor_Parcels/FeatureServer/0/query"
)

FIELD_MAP = {
    "PARCEL_ID": "parcel_id",
    "SITUS_ADDRESS": "address",
    "LOT_AREA": "lot_sf",
    "USE_CODE": "present_use",
    "ZONE": "zone_code",
    "TOTAL_AV": "assessed_value",
    "OWNER_NAME": "owner_name",
}


class SnohomishCountyAgent(BaseIngestAgent):
    county = CountyEnum.snohomish
    endpoint = ENDPOINT
    field_map = FIELD_MAP

    @property
    def out_fields(self) -> str:
        return ",".join(FIELD_MAP.keys())


if __name__ == "__main__":
    import asyncio
    agent = SnohomishCountyAgent()
    result = asyncio.run(agent.run())
    print(result)
