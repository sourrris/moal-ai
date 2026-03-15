from __future__ import annotations

from risk_common.schemas_v2 import RiskEventV2
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import set_tenant_context


class EventEnrichmentService:
    @staticmethod
    async def enrich(session: AsyncSession, event: RiskEventV2) -> tuple[dict, list[str]]:
        await set_tenant_context(session, event.tenant_id)

        signals: dict = {
            "ip_risk_score": 0.0,
            "ip_is_proxy": False,
            "bin_country_mismatch": False,
            "jurisdiction_risk_score": 0.0,
            "sanctions_hit": False,
            "pep_hit": False,
            "fx_rate": 1.0,
        }
        sources: list[str] = []

        if event.transaction.source_ip:
            ip_row = await session.execute(
                text(
                    """
                    SELECT source_name, risk_score, is_proxy, country_code
                    FROM ip_intelligence_cache
                    WHERE ip = :ip
                      AND expires_at >= NOW()
                    LIMIT 1
                    """
                ),
                {"ip": str(event.transaction.source_ip)},
            )
            ip_data = ip_row.first()
            if ip_data:
                mapping = dict(ip_data._mapping)
                signals["ip_risk_score"] = float(mapping.get("risk_score") or 0.0)
                signals["ip_is_proxy"] = bool(mapping.get("is_proxy") or False)
                signals["ip_country"] = mapping.get("country_code")
                sources.append(str(mapping.get("source_name")))

        if event.transaction.card_bin:
            bin_row = await session.execute(
                text(
                    """
                    SELECT source_name, country_code
                    FROM bin_intelligence_cache
                    WHERE bin = :bin
                      AND expires_at >= NOW()
                    LIMIT 1
                    """
                ),
                {"bin": event.transaction.card_bin},
            )
            bin_data = bin_row.first()
            if bin_data:
                mapping = dict(bin_data._mapping)
                bin_country = mapping.get("country_code")
                src_country = event.transaction.source_country
                if bin_country and src_country and str(bin_country).upper() != str(src_country).upper():
                    signals["bin_country_mismatch"] = True
                sources.append(str(mapping.get("source_name")))

        destination_country = event.transaction.destination_country or event.transaction.source_country
        if destination_country:
            jurisdiction_row = await session.execute(
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
                {"jurisdiction": destination_country.upper()},
            )
            jurisdiction = jurisdiction_row.first()
            if jurisdiction:
                mapping = dict(jurisdiction._mapping)
                signals["jurisdiction_risk_score"] = float(mapping.get("risk_score") or 0.0)
                sources.append(str(mapping.get("source_name")))

        merchant_name = (event.transaction.merchant_id or event.transaction.metadata.get("merchant_name") or "").strip()
        if merchant_name:
            sanctions_row = await session.execute(
                text(
                    """
                    SELECT 1
                    FROM sanctions_entities
                    WHERE active = TRUE
                      AND (
                        lower(primary_name) = lower(:merchant_name)
                        OR lower(:merchant_name) = ANY(
                            SELECT lower(alias) FROM unnest(aliases) AS alias
                        )
                      )
                    LIMIT 1
                    """
                ),
                {"merchant_name": merchant_name},
            )
            if sanctions_row.first():
                signals["sanctions_hit"] = True
                sources.append("ofac_sls")

            pep_row = await session.execute(
                text(
                    """
                    SELECT source_name
                    FROM pep_entities
                    WHERE (
                        lower(full_name) = lower(:merchant_name)
                        OR lower(:merchant_name) = ANY(
                            SELECT lower(alias) FROM unnest(aliases) AS alias
                        )
                      )
                    LIMIT 1
                    """
                ),
                {"merchant_name": merchant_name},
            )
            pep_hit = pep_row.first()
            if pep_hit:
                signals["pep_hit"] = True
                sources.append(str(pep_hit[0]) if pep_hit[0] else "pep_entities")

        if event.transaction.currency.upper() != "USD":
            fx_row = await session.execute(
                text(
                    """
                    SELECT rate
                    FROM fx_rates
                    WHERE base_currency = :base_currency
                      AND quote_currency = 'USD'
                    ORDER BY rate_date DESC
                    LIMIT 1
                    """
                ),
                {"base_currency": event.transaction.currency.upper()},
            )
            fx = fx_row.scalar_one_or_none()
            if fx:
                signals["fx_rate"] = float(fx)
                sources.append("ecb_fx")

        return signals, sorted({item for item in sources if item})
