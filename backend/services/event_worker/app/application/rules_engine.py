from __future__ import annotations

from risk_common.schemas_v2 import RiskEventV2


class RulesEngine:
    @staticmethod
    def evaluate(event: RiskEventV2, enrichment: dict) -> tuple[list[str], float]:
        hits: list[str] = []
        rule_score = 0.0

        amount = float(event.transaction.amount)
        if amount >= 10000:
            hits.append("high_amount")
            rule_score += 0.25

        if enrichment.get("sanctions_hit"):
            hits.append("sanctions_match")
            rule_score += 0.8

        if enrichment.get("pep_hit"):
            hits.append("pep_match")
            rule_score += 0.3

        if enrichment.get("ip_is_proxy"):
            hits.append("proxy_ip")
            rule_score += 0.2

        if enrichment.get("bin_country_mismatch"):
            hits.append("bin_country_mismatch")
            rule_score += 0.2

        jurisdiction_risk = float(enrichment.get("jurisdiction_risk_score") or 0.0)
        if jurisdiction_risk >= 0.7:
            hits.append("high_risk_jurisdiction")
            rule_score += 0.25

        if event.transaction.source_country and event.transaction.destination_country:
            if event.transaction.source_country.upper() != event.transaction.destination_country.upper():
                hits.append("cross_border")
                rule_score += 0.1

        rule_score = max(0.0, min(rule_score, 1.0))
        return hits, rule_score


def infer_risk_level(risk_score: float) -> str:
    if risk_score >= 0.85:
        return "critical"
    if risk_score >= 0.65:
        return "high"
    if risk_score >= 0.4:
        return "medium"
    return "low"
