from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str
    kind: Literal["source", "calculation"]
    source_id: str
    data_source: str = "Fuyao"
    endpoint: str
    original_field_name: str | None
    json_path: str | None
    reporting_period: str
    period_end: str
    value: str | None
    unit: str | None
    formula: str | None = None
    input_evidence_ids: list[str] = Field(default_factory=list)
    retrieved_at: datetime
    status: Literal["available", "unavailable"]
    reason: str | None = None
    metadata_json_paths: dict[str, str] = Field(default_factory=dict)


class Metric(BaseModel):
    name: str
    value: str | None
    unit: str = "%"
    status: Literal["available", "unavailable"]
    reason: str | None
    evidence_id: str


class Source(BaseModel):
    source_id: str
    endpoint: str
    parameters: dict
    retrieved_at: datetime
    sha256: str
    raw_json: str
    contract_url: str
    reporting_basis: str = "consolidated"
    unit_basis: str = "Original-currency yuan, verified against the Fuyao financials contract."


class Diagnosis(BaseModel):
    stock_code: str
    status: Literal["complete", "partial", "unavailable"]
    current_year: int | None
    previous_year: int | None
    calculation_version: str = "1"
    decimal_precision: int = 38
    rounding: str = "ROUND_HALF_EVEN; values are unrounded for display"
    issues: list[str]
    metrics: list[Metric]
    evidence: list[Evidence]
    sources: list[Source]
