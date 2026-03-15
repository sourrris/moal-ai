from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class EnrichmentRequest(BaseModel):
    tenant_id: str
    source_ip: str | None = None
    card_bin: str | None = Field(default=None, min_length=6, max_length=12)
    source_country: str | None = None
    destination_country: str | None = None
    merchant_name: str | None = None
    currency: str = "USD"


class FeatureEnrichmentService:
    @staticmethod
    async def enrich(session: AsyncSession, payload: EnrichmentRequest) -> dict:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
            {"tenant_id": payload.tenant_id},
        )

        started = time.perf_counter()
        signals = {
            "ip_risk_score": 0.0,
            "ip_is_proxy": False,
            "bin_country_mismatch": False,
            "jurisdiction_risk_score": 0.0,
            "sanctions_hit": False,
            "pep_hit": False,
            "fx_rate": 1.0,
        }
        provenance: list[dict] = []

        if payload.source_ip:
            row = await session.execute(
                text(
                    """
                    SELECT source_name, risk_score, is_proxy, country_code
                    FROM ip_intelligence_cache
                    WHERE ip = CAST(:ip AS inet)
                      AND expires_at >= NOW()
                    LIMIT 1
                    """
                ),
                {"ip": payload.source_ip},
            )
            item = row.first()
            if item:
                mapping = dict(item._mapping)
                signals["ip_risk_score"] = float(mapping.get("risk_score") or 0.0)
                signals["ip_is_proxy"] = bool(mapping.get("is_proxy") or False)
                signals["ip_country"] = mapping.get("country_code")
                provenance.append(
                    {
                        "source": mapping.get("source_name") or "ip_cache",
                        "field": "source_ip",
                        "cache_hit": True,
                        "latency_ms": 0,
                    }
                )
            else:
                logger.warning("enrichment_cache_miss", extra={"field": "source_ip", "value": payload.source_ip})
                provenance.append({"source": "ip_intelligence_cache", "field": "source_ip", "cache_hit": False, "latency_ms": 0})

        if payload.card_bin:
            row = await session.execute(
                text(
                    """
                    SELECT source_name, country_code
                    FROM bin_intelligence_cache
                    WHERE bin = :bin
                      AND expires_at >= NOW()
                    LIMIT 1
                    """
                ),
                {"bin": payload.card_bin},
            )
            item = row.first()
            if item:
                mapping = dict(item._mapping)
                bin_country = mapping.get("country_code")
                if bin_country and payload.source_country and str(bin_country).upper() != payload.source_country.upper():
                    signals["bin_country_mismatch"] = True
                provenance.append(
                    {
                        "source": mapping.get("source_name") or "bin_cache",
                        "field": "card_bin",
                        "cache_hit": True,
                        "latency_ms": 0,
                    }
                )
            else:
                logger.warning("enrichment_cache_miss", extra={"field": "card_bin", "value": payload.card_bin})
                provenance.append({"source": "bin_intelligence_cache", "field": "card_bin", "cache_hit": False, "latency_ms": 0})

        jurisdiction = payload.destination_country or payload.source_country
        if jurisdiction:
            row = await session.execute(
                text(
                    """
                    SELECT source_name, MAX(risk_score) AS risk_score
                    FROM jurisdiction_risk_scores
                    WHERE jurisdiction_code = :jurisdiction
                    GROUP BY source_name
                    ORDER BY risk_score DESC
                    LIMIT 1
                    """
                ),
                {"jurisdiction": jurisdiction.upper()},
            )
            item = row.first()
            if item:
                mapping = dict(item._mapping)
                signals["jurisdiction_risk_score"] = float(mapping.get("risk_score") or 0.0)
                provenance.append(
                    {
                        "source": mapping.get("source_name") or "jurisdiction_risk",
                        "field": "jurisdiction",
                        "cache_hit": True,
                        "latency_ms": 0,
                    }
                )

        if payload.merchant_name:
            sanctions = await session.execute(
                text(
                    """
                    SELECT source_name
                    FROM sanctions_entities
                    WHERE active = TRUE
                      AND lower(primary_name) = lower(:merchant_name)
                    LIMIT 1
                    """
                ),
                {"merchant_name": payload.merchant_name},
            )
            sanctions_item = sanctions.first()
            if sanctions_item:
                mapping = dict(sanctions_item._mapping)
                signals["sanctions_hit"] = True
                provenance.append(
                    {
                        "source": mapping.get("source_name") or "sanctions",
                        "field": "merchant_name",
                        "cache_hit": True,
                        "latency_ms": 0,
                    }
                )

            pep = await session.execute(
                text(
                    """
                    SELECT source_name
                    FROM pep_entities
                    WHERE active = TRUE
                      AND lower(full_name) = lower(:merchant_name)
                    LIMIT 1
                    """
                ),
                {"merchant_name": payload.merchant_name},
            )
            pep_item = pep.first()
            if pep_item:
                mapping = dict(pep_item._mapping)
                signals["pep_hit"] = True
                provenance.append(
                    {
                        "source": mapping.get("source_name") or "pep",
                        "field": "merchant_name",
                        "cache_hit": True,
                        "latency_ms": 0,
                    }
                )

        if payload.currency.upper() != "USD":
            row = await session.execute(
                text(
                    """
                    SELECT source_name, rate
                    FROM fx_rates
                    WHERE base_currency = :base
                      AND quote_currency = 'USD'
                    ORDER BY rate_date DESC
                    LIMIT 1
                    """
                ),
                {"base": payload.currency.upper()},
            )
            item = row.first()
            if item:
                mapping = dict(item._mapping)
                signals["fx_rate"] = float(mapping.get("rate") or 1.0)
                provenance.append(
                    {
                        "source": mapping.get("source_name") or "fx",
                        "field": "currency",
                        "cache_hit": True,
                        "latency_ms": 0,
                    }
                )

        return {
            "signals": signals,
            "provenance": provenance,
            "enrichment_latency_ms": int((time.perf_counter() - started) * 1000),
        }

