"""Snohomish County parcel ingest agent."""

from openclaw.db.models import CountyEnum
from openclaw.ingest.base import BaseIngestAgent

ENDPOINT = (
    "https://gis.snoco.org/host/rest/services/Hosted/"
    "CADASTRAL__parcels/FeatureServer/0/query"
)

FIELD_MAP = {
    "parcel_id": "parcel_id",
    "situsline1": "address",
    "gis_sq_ft": "lot_sf",
    "usecode": "present_use",
    # No zone field in parcels layer — will need join with zoning layer later
    "mklnd": "assessed_value",
    "ownername": "owner_name",
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
