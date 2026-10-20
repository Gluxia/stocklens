"""Fuyao transport adapted from the original working smoke scripts."""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import requests

from .errors import DiagnosisError

INCOME_ENDPOINT = "https://fuyao.aicubes.cn/api/a-share/financials/income-statements"
SNAPSHOT_ENDPOINT = "https://fuyao.aicubes.cn/api/a-share/prices/snapshot"
CONTRACT_URL = "https://fuyao.aicubes.cn/docs/api-reference/financials/"


@dataclass(frozen=True)
class SourceResponse:
    endpoint: str
    parameters: dict
    retrieved_at: datetime
    raw_json: str
    payload: dict


def reject_constant(value):
    raise ValueError("Nonfinite JSON constant")


class FuyaoClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("FUYAO_API_KEY")

    def _get(self, endpoint: str, parameters: dict) -> SourceResponse:
        if not self.api_key or not self.api_key.strip():
            raise DiagnosisError("missing_api_key", "FUYAO_API_KEY is not configured.", 503)
        try:
            response = requests.get(
                endpoint, params=parameters,
                headers={"X-api-key": self.api_key}, timeout=15,
                allow_redirects=False,
            )
            if response.status_code == 429:
                raise DiagnosisError("upstream_rate_limited", "Fuyao rate limit or quota reached. Wait before retrying.", 429)
            response.raise_for_status()
            if response.status_code != 200:
                raise DiagnosisError("upstream_http_error", "Unexpected Fuyao HTTP response.")
        except requests.Timeout:
            raise DiagnosisError("upstream_timeout", "Fuyao request timed out.", 504) from None
        except requests.RequestException:
            raise DiagnosisError("upstream_http_error", "Fuyao request failed.") from None
        try:
            payload = json.loads(response.text, parse_float=Decimal, parse_constant=reject_constant)
        except (ValueError, TypeError):
            raise DiagnosisError("invalid_json", "Fuyao returned invalid JSON.") from None
        if not isinstance(payload, dict) or type(payload.get("code")) is not int:
            raise DiagnosisError("invalid_response", "Fuyao response envelope is invalid.")
        if payload["code"] != 0:
            if payload["code"] == 429:
                raise DiagnosisError("upstream_rate_limited", "Fuyao rate limit or quota reached. Wait before retrying.", 429)
            # Do not expose provider error messages, which may contain sensitive data.
            raise DiagnosisError("upstream_api_error", "Fuyao returned a nonzero business status.")
        return SourceResponse(endpoint, parameters, datetime.now(timezone.utc), response.text, payload)

    def annual_income_statements(self, stock_code: str) -> SourceResponse:
        return self._get(INCOME_ENDPOINT, {"thscode": stock_code, "period": "annual", "limit": 4})

    def price_snapshot(self, stock_code: str) -> SourceResponse:
        """Preserve the tested snapshot request for later phases; diagnosis does not use it."""
        return self._get(SNAPSHOT_ENDPOINT, {"thscodes": stock_code})
