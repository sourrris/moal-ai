"""Smoke tests for v2 ingestion and decision schemas."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "libs" / "common"))

from risk_common.schemas_v2 import DataSourceRunSummary, DataSourceStatus, RiskEventIngestRequest


def test_risk_event_ingest_schema_normalizes_currency() -> None:
    payload = RiskEventIngestRequest.model_validate(
        {
            "idempotency_key": "idempotency-key-123",
            "source": "gateway",
            "event_type": "transaction",
            "transaction": {
                "amount": 123.45,
                "currency": "usd",
                "card_bin": "400000",
                "card_last4": "1234",
                "metadata": {"channel": "web"},
            },
        }
    )

    assert payload.transaction.currency == "USD"
    assert payload.idempotency_key == "idempotency-key-123"


def test_data_source_status_schema_accepts_health_fields() -> None:
    model = DataSourceStatus.model_validate(
        {
            "source_name": "ofac_sls",
            "enabled": True,
            "cadence_seconds": 900,
            "freshness_slo_seconds": 1200,
            "latest_status": "success",
            "latest_run_at": "2026-02-28T20:00:00Z",
            "last_success_at": "2026-02-28T20:00:00Z",
            "last_failure_at": None,
            "freshness_seconds": 32,
            "consecutive_failures": 0,
            "next_run_at": "2026-02-28T20:15:00Z",
            "degraded_reason": None,
        }
    )
    assert model.source_name == "ofac_sls"
    assert model.freshness_slo_seconds == 1200


def test_data_source_run_summary_schema_accepts_cursor_and_error_summary() -> None:
    model = DataSourceRunSummary.model_validate(
        {
            "run_id": "5cbd8172-ab19-4f21-8dd7-f45f7b3fcb11",
            "source_name": "fatf",
            "status": "failed",
            "started_at": "2026-02-28T21:00:00Z",
            "finished_at": "2026-02-28T21:00:02Z",
            "fetched_records": 0,
            "upserted_records": 0,
            "checksum": "",
            "cursor_state": {"etag": "x"},
            "details": {"error_code": "transient_network"},
            "error_summary": {"error_code": "transient_network"},
        }
    )
    assert model.cursor_state["etag"] == "x"
    assert model.error_summary["error_code"] == "transient_network"
