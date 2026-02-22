"""SQLAlchemy models for Mike's Building System — aligned with v2 schema."""

import enum
import uuid
from datetime import datetime, date

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, Date, DateTime,
    Enum, ForeignKey, UniqueConstraint, PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import declarative_base, relationship, validates

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
    researching = "researching"
    contacted = "contacted"
    negotiating = "negotiating"
    closed_won = "closed_won"
    closed_lost = "closed_lost"
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
    feasibility_results = relationship("FeasibilityResult", back_populates="parcel")


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
    owner_name_canonical = Column(String)
    display_text = Column(Text)
    bundle_data = Column(JSONB)
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
    status = Column(String, default=LeadStatusEnum.new.value, nullable=False)
    owner_phone = Column(String)
    owner_email = Column(String)
    notes = Column(Text)
    contacted_at = Column(DateTime)
    contact_method = Column(String)
    outcome = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="leads")

    @validates("status")
    def validate_status(self, _key, value):
        if isinstance(value, LeadStatusEnum):
            return value.value
        allowed = {s.value for s in LeadStatusEnum}
        if value not in allowed:
            raise ValueError(f"Invalid lead status '{value}'")
        return value


class ScoringRule(Base):
    __tablename__ = "scoring_rules"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    field = Column(String, nullable=False)
    operator = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    action = Column(String, nullable=False)
    tier = Column(String)
    score_adj = Column(Integer, default=0)
    priority = Column(Integer, default=100)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CandidateFeedback(Base):
    __tablename__ = "candidate_feedback"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    rating = Column(String, nullable=False)
    category = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class LearningProposal(Base):
    __tablename__ = "learning_proposals"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(DateTime, default=datetime.utcnow)
    proposal_type = Column(Text)
    description = Column(Text)
    evidence = Column(Text)
    current_value = Column(Text)
    proposed_value = Column(Text)
    confidence = Column(Text)
    estimated_impact = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    reviewed_at = Column(DateTime)
    applied_at = Column(DateTime)


class CandidateNote(Base):
    __tablename__ = "candidate_notes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    note = Column(Text, nullable=False)
    author = Column(Text, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)


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


class FeasibilityResult(Base):
    __tablename__ = "feasibility_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    result_json = Column(JSONB)
    tags = Column(ARRAY(String), default=list)
    best_layout_id = Column(String)
    best_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    parcel = relationship("Parcel", back_populates="feasibility_results")
