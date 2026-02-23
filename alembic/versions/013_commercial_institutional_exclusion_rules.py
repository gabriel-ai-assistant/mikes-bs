"""Seed exclusion rules for commercial, institutional, and non-residential use codes.

Revision ID: 013
Revises: 012
Create Date: 2026-02-23
"""

from alembic import op

revision: str = "013"
down_revision: str = "012"
branch_labels = None
depends_on = None

EXCLUSION_RULES = [
    # Commercial / Retail
    ("Active Retail Trade - Exclude", "present_use", "contains", "retail trade"),
    ("Wholesale Trade - Exclude", "present_use", "contains", "wholesale trade"),
    ("Warehousing Storage - Exclude", "present_use", "contains", "warehousing"),
    ("Mini-Warehouse - Exclude", "present_use", "contains", "mini-warehouse"),
    ("Motor Vehicles Dealer - Exclude", "present_use", "contains", "motor vehicles"),
    ("Drug Store Retail - Exclude", "present_use", "contains", "drug & proprietary"),
    ("Grocery Store - Exclude", "present_use", "contains", "groceries"),
    ("Business Services Commercial - Exclude", "present_use", "contains", "other business services"),
    ("Hardware Farm Equipment - Exclude", "present_use", "contains", "hardware & farm"),
    ("Medical Health Services - Exclude", "present_use", "contains", "health services"),
    ("Professional Services - Exclude", "present_use", "contains", "professional services"),
    ("Communications Commercial - Exclude", "present_use", "contains", "communications nec"),
    # Manufacturing / Industrial
    ("Manufacturing Concrete - Exclude", "present_use", "contains", "concrete, gypsum"),
    ("Manufacturing Drugs Chemical - Exclude", "present_use", "contains", "drugs, chemical"),
    ("Manufacturing Misc NEC - Exclude", "present_use", "contains", "other miscellaneous"),
    # Institutional / Religious
    ("Religious Activities - Exclude", "present_use", "contains", "religious activities"),
    ("Church Synagogue - Exclude", "present_use", "contains", "synagogue"),
    ("Primary Secondary School - Exclude", "present_use", "contains", "primary & secondary school"),
    ("Nursery School - Exclude", "present_use", "contains", "nursery"),
    ("Hospitals - Exclude", "present_use", "contains", "hospital"),
    ("Colleges Universities - Exclude", "present_use", "contains", "college"),
    ("University - Exclude", "present_use", "contains", "university"),
    ("Cemetery - Exclude", "present_use", "contains", "cemetery"),
    # Recreation / Parks
    ("Playgrounds Athletic - Exclude", "present_use", "contains", "playground"),
    ("Athletic Areas - Exclude", "present_use", "contains", "athletic areas"),
    ("Parks General Recreation - Exclude", "present_use", "contains", "parks - general"),
    ("Other Recreation - Exclude", "present_use", "contains", "other recreation"),
    ("Golf Course - Exclude", "present_use", "contains", "golf course"),
    ("Marina - Exclude", "present_use", "contains", "marina"),
]


def upgrade() -> None:
    for name, field, operator, value in EXCLUSION_RULES:
        op.execute(
            f"""
            INSERT INTO scoring_rules (name, field, operator, value, action, score_adj, priority, active)
            VALUES (
                '{name}', '{field}', '{operator}', '{value}',
                'exclude', 0, 10, true
            )
            ON CONFLICT DO NOTHING
            """
        )


def downgrade() -> None:
    names = [r[0] for r in EXCLUSION_RULES]
    placeholders = ", ".join(f"'{n}'" for n in names)
    op.execute(f"DELETE FROM scoring_rules WHERE name IN ({placeholders})")
