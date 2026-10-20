"""Question routing and bounded, evidence-first research orchestration."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .schemas import Diagnosis


class ResearchRequest(BaseModel):
    stock_code: str = Field(default="600519.SH", max_length=20)
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A nonblank research question is required")
        return value


class Dimension(BaseModel):
    id: str
    label: str
    reason: str
    availability: Literal["available", "unavailable"]


class Plan(BaseModel):
    company_name: str = "Kweichow Moutai"
    company_type: str = "Non-financial operating company"
    company_type_basis: str = "Reviewed MVP scope for the single supported company; not an automated industry classification."
    routing_method: str = "Deterministic keyword rules; English and Chinese"
    dimensions: list[Dimension]
    safety_notice: str | None = None


class Finding(BaseModel):
    id: str
    category: Literal["positive", "negative", "mixed", "unknown"]
    kind: Literal["observation", "limitation"]
    title: str
    text: str
    evidence_ids: list[str]
    dimension: str


class Interpretation(BaseModel):
    id: str
    text: str
    evidence_ids: list[str]


class ResearchReport(BaseModel):
    question: str
    plan: Plan
    diagnosis: Diagnosis
    findings: list[Finding]
    observations: list[Finding]
    interpretation_mode: Literal["llm", "deterministic"]
    interpretation_status: str
    interpretations: list[Interpretation]
    freshness: str
    freshness_status: Literal["recent_annual_period", "stale", "unknown"]
    follow_up_questions: list[str]
    disclaimer: str = "Research observations only. No buy/sell recommendations or guaranteed returns. Annual results do not describe current trading conditions."


DIMENSIONS = {
    "growth": ("Growth", ("growth", "grow", "revenue", "sales", "增长", "营收", "收入"), True),
    "profitability": ("Profitability", ("profit", "margin", "earnings", "利润", "盈利", "净利"), True),
    "valuation": ("Valuation", ("valuation", "value", "cheap", "expensive", "p/e", " pe ", "估值", "便宜", "贵吗", "太贵", "昂贵"), False),
    "price": ("Price behavior", ("price", "trend", "momentum", "股价", "走势", "行情"), False),
    "quality": ("Earnings quality & resilience", ("cash", "debt", "quality", "risk", "现金", "负债", "质量", "风险"), False),
}
SAFETY_TERMS = ("buy", "sell", "guarantee", "guaranteed", "should i invest", "recommend", "target price", "买", "卖", "荐股", "保本", "稳赚", "保证收益")


def make_plan(question: str) -> Plan:
    text = question.casefold()
    sensitive = any(term in text for term in SAFETY_TERMS)
    selected = [key for key, (_, keywords, _) in DIMENSIONS.items() if any(word in text for word in keywords)]
    if not selected:
        selected = ["growth", "profitability"]
        reason = "No specific supported dimension matched; the default annual operating-performance review was selected."
    else:
        reason = None
    dimensions = [Dimension(
        id=key, label=DIMENSIONS[key][0],
        reason=reason or f"The question matched {DIMENSIONS[key][0].lower()} keywords.",
        availability="available" if DIMENSIONS[key][2] else "unavailable",
    ) for key in selected]
    if any(key not in ("growth", "profitability") for key in selected):
        for key in ("growth", "profitability"):
            if key not in selected:
                dimensions.append(Dimension(id=key, label=DIMENSIONS[key][0], reason="Included as available annual financial context; it cannot answer the requested unavailable dimension.", availability="available"))
    return Plan(dimensions=dimensions, safety_notice=(
        "This question requests an investment action or certainty. StockLens provides factual research only and will not recommend trades or guarantee returns."
        if sensitive else None
    ))


def freshness(diagnosis: Diagnosis, now: datetime):
    if diagnosis.current_year is None:
        return "unknown", "No annual reporting period is available."
    age = now.year - diagnosis.current_year
    if age > 1:
        return "stale", f"Latest returned annual period is {diagnosis.current_year} FY. It is older than the previous calendar year; more recent filings may be missing."
    if age < 1:
        return "unknown", "The returned period may be incomplete or future-dated. Verify the source dates before relying on it."
    return "recent_annual_period", f"Latest returned annual period is {diagnosis.current_year} FY. Retrieved now does not mean current operations or price data; newer interim filings are not checked."


def factual_report(request: ResearchRequest, diagnosis: Diagnosis, now: datetime | None = None) -> ResearchReport:
    plan = make_plan(request.question)
    selected = {dimension.id for dimension in plan.dimensions}
    findings = []
    observations = []
    metrics = {metric.name: metric for metric in diagnosis.metrics}
    evidence = {item.evidence_id: item for item in diagnosis.evidence}
    names = {"revenue_growth": "Revenue growth", "net_profit_growth": "Net profit growth", "net_profit_margin": "Net profit margin"}
    signs = {}
    for key, metric in metrics.items():
        dimension = "profitability" if key == "net_profit_margin" else "growth"
        if dimension not in selected:
            continue
        ev = evidence.get(metric.evidence_id)
        valid = ev is not None and ev.status == "available" and metric.status == "available" and metric.value is not None
        if not valid:
            findings.append(Finding(id=key, category="unknown", kind="limitation", title=f"{names[key]} unavailable", text=(metric.reason or "Insufficient validated evidence").replace("_", " "), evidence_ids=[metric.evidence_id] if ev else [], dimension=dimension))
            continue
        value = Decimal(metric.value)
        observation = Finding(id=key, category="unknown", kind="observation", title=names[key], text=f"{names[key]} is {metric.value}{metric.unit} for {ev.reporting_period}.", evidence_ids=[metric.evidence_id], dimension=dimension)
        observations.append(observation)
        if key != "net_profit_margin" and value != 0:
            signs[key] = value > 0
            findings.append(Finding(id=key, category="positive" if value > 0 else "negative", kind="observation", title=f"{names[key].replace(' growth', '')} {'increased' if value > 0 else 'decreased'} year over year", text=observation.text + " Direction refers only to this annual comparison, not investment attractiveness.", evidence_ids=observation.evidence_ids, dimension=dimension))
    if len(signs) == 2 and len(set(signs.values())) == 2:
        findings.append(Finding(id="divergent_growth", category="mixed", kind="observation", title="Revenue and profit moved in opposite directions", text="The annual growth signals diverge. These measures do not establish the cause of the divergence.", evidence_ids=[metrics[key].evidence_id for key in signs], dimension="growth"))
    for dimension in plan.dimensions:
        if dimension.availability == "unavailable":
            findings.append(Finding(id=f"missing_{dimension.id}", category="unknown", kind="limitation", title=f"{dimension.label} not verified", text="This release has no verified data adapter for this dimension. Annual income statements cannot answer it.", evidence_ids=[], dimension=dimension.id))
    findings.append(Finding(id="margin_context", category="unknown", kind="limitation", title="Peer and historical context not assessed", text="An absolute margin alone does not establish competitive strength, valuation, or investment suitability. Peer benchmarks and a longer historical assessment are unavailable.", evidence_ids=[metrics["net_profit_margin"].evidence_id] if "net_profit_margin" in metrics else [], dimension="profitability"))
    status, freshness_text = freshness(diagnosis, now or datetime.now(timezone.utc))
    if status != "recent_annual_period":
        findings.append(Finding(id="freshness", category="unknown", kind="limitation", title="Reporting freshness requires verification", text=freshness_text, evidence_ids=[metric.evidence_id for metric in diagnosis.metrics], dimension="data_quality"))
    return ResearchReport(
        question=request.question, plan=plan, diagnosis=diagnosis, findings=findings, observations=observations,
        interpretation_mode="deterministic", interpretation_status="AI is not configured; displaying deterministic factual observations.",
        interpretations=[], freshness=freshness_text, freshness_status=status,
        follow_up_questions=["How did revenue and net profit growth compare?", "What does the reported net profit margin establish?", "What evidence is missing to assess valuation?", "Can the available statements establish cash-flow quality?"],
    )


def interpretation_catalog(report: ResearchReport) -> list[Interpretation]:
    """Only interpretations whose conditions were established by Python are candidates."""
    candidates = []
    for finding in report.findings:
        if finding.category in ("positive", "negative"):
            candidates.append(Interpretation(
                id=f"interpret_{finding.id}",
                text=("The annual comparison shows expansion in this measure. It does not establish persistence, the underlying cause, or investment attractiveness."
                      if finding.category == "positive" else
                      "The annual comparison shows contraction in this measure. Additional evidence is needed to establish its cause or persistence."),
                evidence_ids=finding.evidence_ids,
            ))
        elif finding.category == "mixed":
            candidates.append(Interpretation(id="interpret_divergence", text="Revenue and profit signals should be considered together. Their divergence prevents a uniformly positive or negative reading of annual growth; causes remain unverified.", evidence_ids=finding.evidence_ids))
    margin = next((observation for observation in report.observations if observation.id == "net_profit_margin"), None)
    if margin:
        candidates.append(Interpretation(id="interpret_margin", text="The reported margin describes consolidated accounting profitability. It does not establish cash generation or relative competitive strength without additional evidence.", evidence_ids=margin.evidence_ids))
    return candidates
