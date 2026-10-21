"""Deterministic answer contract, optional on existing research responses."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .errors import DiagnosisError
from .stocks import get_stock

IntentId = Literal[
    'price_performance', 'growth_comparison', 'margin_meaning',
    'valuation_evidence_gap', 'cashflow_support', 'manufacturing_evidence_gap',
    'price_causality', 'unsupported',
]
AnswerStatus = Literal['answered', 'partial', 'unavailable']
Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class MissingEvidence(ContractModel):
    # A gap code is a capability/data requirement, never an invented source evidence ID.
    code: Nonblank
    description: Nonblank
    reason: Literal['not_supported', 'not_returned', 'invalid', 'period_mismatch', 'unverified', 'provider_failure']


class AnswerScope(ContractModel):
    stock_code: str
    reporting_periods: list[Nonblank] = Field(default_factory=list)
    price_requested_start: date | None = None
    price_requested_end: date | None = None
    price_observed_start: date | None = None
    price_observed_end: date | None = None
    time_zone: Literal['Asia/Shanghai'] = 'Asia/Shanghai'
    assumptions: list[Nonblank] = Field(default_factory=list)

    @field_validator('stock_code')
    @classmethod
    def supported_stock(cls, value):
        try:
            get_stock(value)
        except DiagnosisError:
            raise ValueError('Unsupported research stock') from None
        return value

    @model_validator(mode='after')
    def valid_intervals(self):
        for start, end in ((self.price_requested_start, self.price_requested_end),
                           (self.price_observed_start, self.price_observed_end)):
            if (start is None) != (end is None) or (start is not None and start > end):
                raise ValueError('An interval requires ordered start and end dates')
        if self.price_requested_start and self.price_observed_start:
            if not self.price_requested_start <= self.price_observed_start <= self.price_observed_end <= self.price_requested_end:
                raise ValueError('Observed dates must lie within the requested interval')
        # Matching endpoints never establish trading-calendar completeness.
        return self


class Answer(ContractModel):
    intent_id: IntentId
    answer_status: AnswerStatus
    direct_answer: Nonblank
    supporting_evidence_ids: list[Nonblank] = Field(default_factory=list)
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)
    scope: AnswerScope

    @field_validator('supporting_evidence_ids')
    @classmethod
    def unique_references(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('Evidence references must be unique')
        return values

    @model_validator(mode='after')
    def explain_incomplete_answer(self):
        if self.answer_status != 'answered' and not self.missing_evidence:
            raise ValueError('An incomplete answer requires an explicit evidence gap')
        # Do not derive answer status from financial completeness, AI mode or scope dates.
        # The report builder validates source identity, availability and semantic sufficiency.
        return self
