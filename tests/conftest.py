"""Test configuration: stub out DB and heavy dependencies before any imports."""
import sys
from unittest.mock import MagicMock

# Stub psycopg2 so session.py can create the engine without a real DB
if 'psycopg2' not in sys.modules:
    sys.modules['psycopg2'] = MagicMock()
    sys.modules['psycopg2.extensions'] = MagicMock()
    sys.modules['psycopg2.extras'] = MagicMock()

# Stub geoalchemy2 and shapely (heavy geo deps not needed for unit tests)
for mod in ('geoalchemy2', 'geoalchemy2.types', 'shapely', 'shapely.geometry',
            'geopandas'):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
