"""Skagit County parcel ingest agent.

TODO: The ArcGIS REST endpoint for Skagit County parcels has not been verified.
To find it:
1. Visit https://www.skagitcounty.net/GIS/
2. Look for "ArcGIS REST Services" or "Open Data Portal"
3. Find the parcel/assessor layer endpoint
4. Update ENDPOINT below with the confirmed URL
5. Update FIELD_MAP to match actual field names from the service

Alternatively, check:
- https://hub.arcgis.com/ and search "Skagit County parcels"
- https://services.arcgis.com/ endpoints linked from county GIS page
"""

from openclaw.db.models import CountyEnum
from openclaw.ingest.base import BaseIngestAgent

# TODO: Replace with verified endpoint — see docstring above
ENDPOINT = ""

FIELD_MAP = {
    "PARCEL_ID": "parcel_id",
    "SITUS_ADDRESS": "address",
    "LOT_AREA": "lot_sf",
    "USE_CODE": "present_use",
    "ZONE": "zone_code",
    "TOTAL_AV": "assessed_value",
    "OWNER_NAME": "owner_name",
}


class SkagitCountyAgent(BaseIngestAgent):
    county = CountyEnum.skagit
    endpoint = ENDPOINT
    field_map = FIELD_MAP

    @property
    def out_fields(self) -> str:
        return ",".join(FIELD_MAP.keys())

    async def run(self) -> dict:
        if not self.endpoint:
            raise NotImplementedError(
                "Skagit County ArcGIS endpoint not yet configured. "
                "See skagit.py docstring for instructions to find and set it."
            )
        return await super().run()


if __name__ == "__main__":
    import asyncio
    agent = SkagitCountyAgent()
    result = asyncio.run(agent.run())
    print(result)
