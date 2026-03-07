from __future__ import annotations

from risk_common.schemas_v2 import RiskEventV2


class RulesEngine:
    @staticmethod
    def evaluate(event: RiskEventV2, enrichment: dict, *, overrides: dict | None = None) -> tuple[list[str], float]:
        policy = overrides or {}
        hits: list[str] = []
        rule_score = 0.0

        high_amount_threshold = float(policy.get("high_amount_threshold") or 10000)
        high_amount_weight = float(policy.get("high_amount_weight") or 0.25)
        sanctions_weight = float(policy.get("sanctions_weight") or 0.8)
        pep_weight = float(policy.get("pep_weight") or 0.3)
        proxy_ip_weight = float(policy.get("proxy_ip_weight") or 0.2)
        bin_mismatch_weight = float(policy.get("bin_mismatch_weight") or 0.2)
        jurisdiction_threshold = float(policy.get("jurisdiction_threshold") or 0.7)
        jurisdiction_weight = float(policy.get("jurisdiction_weight") or 0.25)
        cross_border_weight = float(policy.get("cross_border_weight") or 0.1)

        amount = float(event.transaction.amount)
        if amount >= high_amount_threshold:
            hits.append("high_amount")
            rule_score += high_amount_weight

        if enrichment.get("sanctions_hit"):
            hits.append("sanctions_match")
            rule_score += sanctions_weight

        if enrichment.get("pep_hit"):
            hits.append("pep_match")
            rule_score += pep_weight

        if enrichment.get("ip_is_proxy"):
            hits.append("proxy_ip")
            rule_score += proxy_ip_weight

        if enrichment.get("bin_country_mismatch"):
            hits.append("bin_country_mismatch")
            rule_score += bin_mismatch_weight

        jurisdiction_risk = float(enrichment.get("jurisdiction_risk_score") or 0.0)
        if jurisdiction_risk >= jurisdiction_threshold:
            hits.append("high_risk_jurisdiction")
            rule_score += jurisdiction_weight

        if event.transaction.source_country and event.transaction.destination_country:
            if event.transaction.source_country.upper() != event.transaction.destination_country.upper():
                hits.append("cross_border")
                rule_score += cross_border_weight

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
