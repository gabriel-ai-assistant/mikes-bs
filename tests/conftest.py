"""Test configuration: stub out DB and heavy dependencies before any imports."""
import sys
import importlib
from unittest.mock import MagicMock

# Stub psycopg2 so session.py can create the engine without a real DB
if 'psycopg2' not in sys.modules:
    sys.modules['psycopg2'] = MagicMock()
    sys.modules['psycopg2.extensions'] = MagicMock()
    sys.modules['psycopg2.extras'] = MagicMock()

# Stub geoalchemy2 and shapely only if they are not actually installed.
# This allows test_ingest.py (which uses real geopandas/shapely) to work
# when the packages are present, while still letting the rest of the suite
# run in environments without the heavy geo stack.
for mod in ('geoalchemy2', 'geoalchemy2.types', 'shapely', 'shapely.geometry',
            'geopandas'):
    if mod not in sys.modules:
        try:
            importlib.import_module(mod)
        except ImportError:
            sys.modules[mod] = MagicMock()
