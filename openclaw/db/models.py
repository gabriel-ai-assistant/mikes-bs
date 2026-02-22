"""SQLAlchemy models for Mike's Building System — aligned with v2 schema."""

import enum
import uuid
from datetime import datetime, date

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, Date, DateTime,
    Enum, ForeignKey, UniqueConstraint, PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class CountyEnum(enum.Enum):
    king = "king"
    snohomish = "snohomish"
    skagit = "skagit"


class ScoreTierEnum(enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class LeadStatusEnum(enum.Enum):
    new = "new"
    reviewed = "reviewed"
    outreach = "outreach"
    active = "active"
    dead = "dead"


class Parcel(Base):
    __tablename__ = "parcels"
    __table_args__ = (UniqueConstraint("parcel_id", "county", name="uq_parcel_county"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parcel_id = Column(String, nullable=False, index=True)
    county = Column(Enum(CountyEnum), nullable=False)
    lrsn = Column(String)
    corrdate = Column(DateTime)
    address = Column(String)
    owner_name = Column(String)
    owner_address = Column(String)   # full mailing address
    lot_sf = Column(Float)
    frontage_ft = Column(Float)
    parcel_width_ft = Column(Float)
    zone_code = Column(String)
    present_use = Column(String)
    assessed_value = Column(Integer)
    improvement_value = Column(Integer)
    total_value = Column(Integer)
    last_sale_price = Column(Integer)
    last_sale_date = Column(Date)
    geometry = Column(Geometry("GEOMETRY", srid=4326))
    ingested_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidates = relationship("Candidate", back_populates="parcel")


class ZoningRule(Base):
    __tablename__ = "zoning_rules"
    __table_args__ = (PrimaryKeyConstraint("county", "zone_code"),)

    county = Column(String, nullable=False)
    zone_code = Column(String, nullable=False)
    min_lot_sf = Column(Integer)
    min_lot_width_ft = Column(Integer)
    max_du_per_acre = Column(Float)
    notes = Column(String)


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=False)
    score_tier = Column(Enum(ScoreTierEnum))
    score = Column(Integer, default=0)
    potential_splits = Column(Integer)
    splits_min = Column(Integer)
    splits_max = Column(Integer)
    splits_confidence = Column(String(10))
    subdivision_access_mode = Column(String(20))
    arbitrage_depth_score = Column(Integer)
    economic_margin_pct = Column(Float)
    estimated_land_value = Column(Integer)
    estimated_dev_cost = Column(Integer)
    estimated_build_cost = Column(Integer)
    estimated_arv = Column(Integer)
    estimated_profit = Column(Integer)
    estimated_margin_pct = Column(Float)
    has_critical_area_overlap = Column(Boolean, default=False)
    has_shoreline_overlap = Column(Boolean, default=False)
    flagged_for_review = Column(Boolean, default=False)
    tags = Column(ARRAY(String), default=list)
    reason_codes = Column(ARRAY(String), default=list)
    subdivisibility_score = Column(Integer, default=0)
    subdivision_feasibility = Column(String(20), default="UNKNOWN")
    subdivision_flags = Column(ARRAY(String), default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    parcel = relationship("Parcel", back_populates="candidates")
    leads = relationship("Lead", back_populates="candidate")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    status = Column(Enum(LeadStatusEnum), default=LeadStatusEnum.new)
    owner_phone = Column(String)
    owner_email = Column(String)
    notes = Column(Text)
    contacted_at = Column(DateTime)
    contact_method = Column(String)
    outcome = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="leads")


class CriticalArea(Base):
    __tablename__ = "critical_areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String)
    area_type = Column(String)
    geometry = Column(Geometry("GEOMETRY", srid=4326))


class ShorelineBuffer(Base):
    __tablename__ = "shoreline_buffer"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    geometry = Column(Geometry("GEOMETRY", srid=4326))


class RutaBoundary(Base):
    __tablename__ = "ruta_boundaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    geometry = Column(Geometry("GEOMETRY", srid=4326))
