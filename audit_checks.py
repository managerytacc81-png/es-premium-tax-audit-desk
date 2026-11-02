#!/usr/bin/env python3
"""
E&S Premium-Tax Audit Desk - Core Rules Engine & Reconciliation Module
(slug: es-premium-tax-audit-desk)

Performs forensic surplus lines compliance audits:
1. Unreported carrier/inspection/policy fees (AK Bulletin 04-14, TX TIC § 981.008, CA Ins Code § 1765.2, FL § 626.932)
2. Late regulatory & stamping office filings (TX 60d, CA 30d, NY 45d, FL 30d)
3. Return-premium credit sweeps (GA credit-only O.C.G.A. § 33-5-31, AL amended ID-15, SC quarterly negative endorsement)
4. Missing / defective Exempt Commercial Purchaser (ECP) documentation (15 U.S.C. § 8206, TIC § 981.0031)
5. NRRA Home-State multi-state allocation violations (Dodd-Frank § 521, 15 U.S.C. § 8201)

Reconciliation Module:
Forensically matches stamping office extracts (SLTX, ELANY, FSLSO SLIP) against broker annual tax returns (FIN317, Form 11-13).
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class PolicyRecord:
    policy_no: str
    insured_name: str
    insured_hq_state: str
    risk_states: List[str]
    premium: float
    carrier_fees: float = 0.0
    effective_date: str = ""
    filed_date: Optional[str] = None
    cancellations_returns: float = 0.0
    ecp_flag: bool = False
    ecp_documented: bool = False
    tax_remitted: float = 0.0
    carrier_fee_taxed: bool = False
    state_allocated_taxes: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRecord":
        risk_raw = data.get("risk_states", "")
        if isinstance(risk_raw, list):
            risk_states = [str(s).strip().upper() for s in risk_raw if str(s).strip()]
        elif isinstance(risk_raw, str):
            risk_states = [s.strip().upper() for s in risk_raw.split(",") if s.strip()]
        else:
            risk_states = []

        def _to_float(v: Any) -> float:
            if v is None or v == "":
                return 0.0
            return float(str(v).replace("$", "").replace(",", "").strip())

        def _to_bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("true", "1", "yes", "y", "t")

        allocated_raw = data.get("state_allocated_taxes", {})
        if isinstance(allocated_raw, str) and allocated_raw:
            try:
                allocated_taxes = json.loads(allocated_raw)
            except Exception:
                allocated_taxes = {}
        elif isinstance(allocated_raw, dict):
            allocated_taxes = {k.upper(): float(v) for k, v in allocated_raw.items()}
        else:
            allocated_taxes = {}

        return cls(
            policy_no=str(data.get("policy_no", "")).strip(),
            insured_name=str(data.get("insured_name", "Insured Entity")).strip(),
            insured_hq_state=str(data.get("insured_hq_state", "")).strip().upper(),
            risk_states=risk_states,
            premium=_to_float(data.get("premium", 0.0)),
            carrier_fees=_to_float(data.get("carrier_fees", 0.0)),
            effective_date=str(data.get("effective_date", "")).strip(),
            filed_date=str(data.get("filed_date", "")).strip() if data.get("filed_date") else None,
            cancellations_returns=_to_float(data.get("cancellations_returns", 0.0)),
            ecp_flag=_to_bool(data.get("ecp_flag", False)),
            ecp_documented=_to_bool(data.get("ecp_documented", False)),
            tax_remitted=_to_float(data.get("tax_remitted", 0.0)),
            carrier_fee_taxed=_to_bool(data.get("carrier_fee_taxed", False)),
            state_allocated_taxes=allocated_taxes,
        )


@dataclass
class AuditFinding:
    finding_id: str
    policy_no: str
    insured_name: str
    violation_type: str
    state: str
    statute_cite: str
    description: str
    estimated_tax_at_risk: float
    potential_penalty: float
    total_financial_exposure: float
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW", "OPPORTUNITY_CREDIT"
    remediation_path: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StampingFilingItem:
    filing_id: str
    policy_no: str
    insured_name: str
    transaction_type: str  # "NEW", "RENEWAL", "ENDORSEMENT", "CANCELLATION"
    effective_date: str
    stamped_date: str
    gross_premium: float
    carrier_fees: float
    stamping_fee: float
    calculated_tax: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StampingFilingItem":
        def _to_float(v: Any) -> float:
            if v is None or v == "":
                return 0.0
            return float(str(v).replace("$", "").replace(",", "").strip())

        return cls(
            filing_id=str(data.get("filing_id", "")).strip(),
            policy_no=str(data.get("policy_no", "")).strip(),
            insured_name=str(data.get("insured_name", "")).strip(),
            transaction_type=str(data.get("transaction_type", "NEW")).strip().upper(),
            effective_date=str(data.get("effective_date", "")).strip(),
            stamped_date=str(data.get("stamped_date", "")).strip(),
            gross_premium=_to_float(data.get("gross_premium", 0.0)),
            carrier_fees=_to_float(data.get("carrier_fees", 0.0)),
            stamping_fee=_to_float(data.get("stamping_fee", 0.0)),
            calculated_tax=_to_float(data.get("calculated_tax", 0.0)),
        )


@dataclass
class AnnualTaxReturnSummary:
    state_code: str
    reporting_year: int
    form_name: str  # e.g., "FIN317" (TX), "Form 11-13" (NY), "TAX-1" (CA)
    reported_gross_premium: float
    reported_carrier_fees: float
    reported_taxable_premium: float
    tax_rate: float
    total_tax_liability: float
    prepayments_credited: float
    return_premium_credits_claimed: float
    net_tax_paid: float
    reported_policies: List[str] = field(default_factory=list)


@dataclass
class ReconciliationDiscrepancy:
    discrepancy_type: str
    identifier: str
    stamping_value: float
    tax_return_value: float
    variance: float
    statute_cite: str
    explanation: str
    action_required: str


@dataclass
class ReconciliationReport:
    state_code: str
    reporting_year: int
    form_name: str
    stamping_total_policies: int
    tax_return_total_policies: int
    stamping_gross_premium: float
    tax_return_gross_premium: float
    premium_variance: float
    stamping_carrier_fees: float
    tax_return_carrier_fees: float
    carrier_fees_variance: float
    stamping_total_tax_base: float
    tax_return_tax_base: float
    net_tax_base_variance: float
    estimated_tax_shortfall_or_credit: float
    unreported_stamped_policies: List[str]
    unstamped_reported_policies: List[str]
    unclaimed_return_premium_credits: float
    discrepancies: List[ReconciliationDiscrepancy]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_code": self.state_code,
            "reporting_year": self.reporting_year,
            "form_name": self.form_name,
            "stamping_total_policies": self.stamping_total_policies,
            "tax_return_total_policies": self.tax_return_total_policies,
            "stamping_gross_premium": round(self.stamping_gross_premium, 2),
            "tax_return_gross_premium": round(self.tax_return_gross_premium, 2),
            "premium_variance": round(self.premium_variance, 2),
            "stamping_carrier_fees": round(self.stamping_carrier_fees, 2),
            "tax_return_carrier_fees": round(self.tax_return_carrier_fees, 2),
            "carrier_fees_variance": round(self.carrier_fees_variance, 2),
            "stamping_total_tax_base": round(self.stamping_total_tax_base, 2),
            "tax_return_tax_base": round(self.tax_return_tax_base, 2),
            "net_tax_base_variance": round(self.net_tax_base_variance, 2),
            "estimated_tax_shortfall_or_credit": round(self.estimated_tax_shortfall_or_credit, 2),
            "unreported_stamped_policies": self.unreported_stamped_policies,
            "unstamped_reported_policies": self.unstamped_reported_policies,
            "unclaimed_return_premium_credits": round(self.unclaimed_return_premium_credits, 2),
            "discrepancies_count": len(self.discrepancies),
            "discrepancies": [asdict(d) for d in self.discrepancies],
        }


class PremiumTaxRulesEngine:
    def __init__(self, states_db_path: Optional[Path] = None):
        if states_db_path is None:
            states_db_path = Path(__file__).resolve().parent / "rules_db" / "states.json"
        
        with open(states_db_path, "r", encoding="utf-8") as f:
            self.states_db = json.load(f)

    def get_state_rule(self, state_code: str) -> Dict[str, Any]:
        code = state_code.upper().strip()
        if code not in self.states_db:
            raise ValueError(f"State code '{state_code}' not recognized in 50 states + DC rules database.")
        return self.states_db[code]

    def _parse_date(self, d_str: Optional[str]) -> Optional[date]:
        if not d_str:
            return None
        d_clean = d_str.strip().split("T")[0]
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(d_clean, fmt).date()
            except ValueError:
                continue
        return None

    def audit_policy(self, policy: PolicyRecord) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        state_rule = self.get_state_rule(policy.insured_hq_state)
        tax_rate = state_rule["tax_rate"] / 100.0
        stamping_fee_pct = (state_rule["stamping_fee_pct"] / 100.0) if state_rule["stamping_office"] else 0.0

        finding_counter = 1

        # -------------------------------------------------------------
        # CHECK 1: UNREPORTED CARRIER / INSPECTION FEES
        # AK Bulletin 04-14, TIC § 981.008, Cal Ins Code § 1765.2, FL § 626.932
        # -------------------------------------------------------------
        if policy.carrier_fees > 0 and not policy.carrier_fee_taxed:
            underpaid_tax = round(policy.carrier_fees * tax_rate, 2)
            underpaid_stamping = round(policy.carrier_fees * stamping_fee_pct, 2)
            statutory_penalty = round(underpaid_tax * 0.10, 2)  # Standard 10% statutory penalty
            total_exposure = round(underpaid_tax + underpaid_stamping + statutory_penalty, 2)

            findings.append(
                AuditFinding(
                    finding_id=f"{policy.policy_no}-F{finding_counter:02d}",
                    policy_no=policy.policy_no,
                    insured_name=policy.insured_name,
                    violation_type="UNREPORTED_CARRIER_FEE",
                    state=policy.insured_hq_state,
                    statute_cite=state_rule["statutory_cite"],
                    description=(
                        f"Carrier/inspection fees of ${policy.carrier_fees:,.2f} omitted from taxable premium base. "
                        f"In {state_rule['state_name']}, premium base includes all policy fees and carrier charges."
                    ),
                    estimated_tax_at_risk=round(underpaid_tax + underpaid_stamping, 2),
                    potential_penalty=statutory_penalty,
                    total_financial_exposure=total_exposure,
                    severity="HIGH",
                    remediation_path=(
                        f"Amend {state_rule['state_name']} tax return and stamping report to include ${policy.carrier_fees:,.2f} "
                        f"carrier fees in taxable premium. Remit ${underpaid_tax:,.2f} tax + ${underpaid_stamping:,.2f} fee "
                        f"prior to state DOI examination to prevent doubled penalties under market conduct audit."
                    ),
                )
            )
            finding_counter += 1

        # -------------------------------------------------------------
        # CHECK 2: LATE FILING DEADLINE AUDIT
        # CA 30d, TX 60d, FL 30d, NY 45d
        # Enforcement context: Alaska DOI D25-09 (Aon Risk $60K penalty, 216 violations)
        # -------------------------------------------------------------
        eff_dt = self._parse_date(policy.effective_date)
        filed_dt = self._parse_date(policy.filed_date)
        deadline_days = state_rule["filing_deadline_days"]

        if eff_dt and filed_dt:
            days_elapsed = (filed_dt - eff_dt).days
            if days_elapsed > deadline_days:
                days_late = days_elapsed - deadline_days
                # Penalty math: estimate based on state precedent ($50-$250 per late filing or 5-10% of tax)
                tax_on_policy = (policy.premium + policy.carrier_fees) * tax_rate
                penalty_estimate = max(100.0, min(1000.0, round(tax_on_policy * 0.10 + (days_late * 5.0), 2)))
                findings.append(
                    AuditFinding(
                        finding_id=f"{policy.policy_no}-F{finding_counter:02d}",
                        policy_no=policy.policy_no,
                        insured_name=policy.insured_name,
                        violation_type="LATE_FILING",
                        state=policy.insured_hq_state,
                        statute_cite=state_rule["statutory_cite"],
                        description=(
                            f"Filing submitted {days_elapsed} days post-effective date (statutory limit is {deadline_days} days). "
                            f"Exceeded statutory deadline by {days_late} days."
                        ),
                        estimated_tax_at_risk=0.0,
                        potential_penalty=penalty_estimate,
                        total_financial_exposure=penalty_estimate,
                        severity="MEDIUM" if days_late <= 30 else "HIGH",
                        remediation_path=(
                            f"Execute retroactive late filing disclosure with {state_rule.get('stamping_office_name') or state_rule['state_name'] + ' DOI'}. "
                            f"Cite justifiable administrative cause or file voluntary self-disclosure under established safe harbor rules."
                        ),
                    )
                )
                finding_counter += 1
        elif eff_dt and not filed_dt:
            today = date.today()
            days_elapsed = (today - eff_dt).days
            if days_elapsed > deadline_days:
                tax_on_policy = (policy.premium + policy.carrier_fees) * tax_rate
                penalty_estimate = max(250.0, round(tax_on_policy * 0.20, 2))
                findings.append(
                    AuditFinding(
                        finding_id=f"{policy.policy_no}-F{finding_counter:02d}",
                        policy_no=policy.policy_no,
                        insured_name=policy.insured_name,
                        violation_type="LATE_FILING",
                        state=policy.insured_hq_state,
                        statute_cite=state_rule["statutory_cite"],
                        description=(
                            f"Unfiled surplus lines policy! {days_elapsed} days have elapsed since policy inception "
                            f"(limit: {deadline_days} days). Zero stamping office or tax record detected."
                        ),
                        estimated_tax_at_risk=round(tax_on_policy, 2),
                        potential_penalty=penalty_estimate,
                        total_financial_exposure=round(tax_on_policy + penalty_estimate, 2),
                        severity="CRITICAL",
                        remediation_path=(
                            f"Immediately submit policy documentation to {state_rule.get('stamping_office_name') or 'DOI'} "
                            f"and remit overdue tax of ${tax_on_policy:,.2f} before receipt of inquiry letter or market conduct audit subpoena."
                        ),
                    )
                )
                finding_counter += 1

        # -------------------------------------------------------------
        # CHECK 3: RETURN-PREMIUM CREDIT CAPTURE SWEEP
        # GA credit-only O.C.G.A. § 33-5-31; AL amended ID-15; SC quarterly negative endorsement
        # -------------------------------------------------------------
        return_prem_amt = abs(policy.cancellations_returns)
        if return_prem_amt > 0:
            unclaimed_tax_credit = round(return_prem_amt * tax_rate, 2)
            unclaimed_stamping_credit = round(return_prem_amt * stamping_fee_pct, 2)
            total_recoverable_credit = round(unclaimed_tax_credit + unclaimed_stamping_credit, 2)

            mechanics = state_rule["return_premium_credit_mechanics"]
            details = state_rule.get("return_premium_details", "")

            findings.append(
                AuditFinding(
                    finding_id=f"{policy.policy_no}-F{finding_counter:02d}",
                    policy_no=policy.policy_no,
                    insured_name=policy.insured_name,
                    violation_type="UNCLAIMED_RETURN_PREMIUM",
                    state=policy.insured_hq_state,
                    statute_cite=state_rule["statutory_cite"],
                    description=(
                        f"Unclaimed return-premium credit of ${total_recoverable_credit:,.2f} identified from cancellation/endorsement "
                        f"reduction of ${return_prem_amt:,.2f}. State credit mechanism: [{mechanics}]. {details}"
                    ),
                    estimated_tax_at_risk=-total_recoverable_credit,  # negative indicates money broker is owed!
                    potential_penalty=0.0,
                    total_financial_exposure=total_recoverable_credit,
                    severity="OPPORTUNITY_CREDIT",
                    remediation_path=(
                        f"Execute {state_rule['state_name']} specific credit capture: "
                        f"{'File amended Form ID-15 schedule' if mechanics == 'amended-return' else 'Offset against subsequent quarterly filing' if mechanics == 'credit-only' else 'Enter negative endorsement in quarterly summary' if mechanics == 'negative-endorsement' else 'Claim credit on annual return Form FIN317'}. "
                        f"Directly recovers ${total_recoverable_credit:,.2f} in cash / tax credits for wholesale broker."
                    ),
                )
            )
            finding_counter += 1

        # -------------------------------------------------------------
        # CHECK 4: MISSING / DEFECTIVE ECP DOCUMENTATION
        # TIC 981.0031 / NRRA 15 U.S.C. § 8206 (>$100k premium, net worth >$20M, qualified risk manager)
        # -------------------------------------------------------------
        if policy.ecp_flag and not policy.ecp_documented:
            tax_at_risk = round(policy.premium * tax_rate, 2)
            statutory_penalties = 2500.0  # Administrative penalty for unauthorized placement / defective exemption
            findings.append(
                AuditFinding(
                    finding_id=f"{policy.policy_no}-F{finding_counter:02d}",
                    policy_no=policy.policy_no,
                    insured_name=policy.insured_name,
                    violation_type="MISSING_ECP_DOCUMENTATION",
                    state=policy.insured_hq_state,
                    statute_cite=state_rule.get("ecp_statutory_cite") or "15 U.S.C. § 8206",
                    description=(
                        f"Policy treated as Exempt Commercial Purchaser (ECP) without verified certification affidavit on file. "
                        f"Under {state_rule['state_name']} law, bypassing diligent search requires signed documentation of risk manager "
                        f"and statutory size thresholds ($100k nationwide premium + $20M net worth or $50M revenue)."
                    ),
                    estimated_tax_at_risk=tax_at_risk,
                    potential_penalty=statutory_penalties,
                    total_financial_exposure=round(tax_at_risk + statutory_penalties, 2),
                    severity="CRITICAL",
                    remediation_path=(
                        f"Issue urgent 30-day ECP certification notice to insured. Obtain counter-signed qualification affidavit "
                        f"confirming statutory metrics and qualified risk manager retention to cure exemption file before audit."
                    ),
                )
            )
            finding_counter += 1

        # -------------------------------------------------------------
        # CHECK 5: INCORRECT HOME-STATE MULTI-STATE ALLOCATION (NRRA § 521)
        # 100% of premium tax is payable solely to Home State. Allocating across risk states is unlawful.
        # -------------------------------------------------------------
        if policy.state_allocated_taxes:
            # If broker remitted tax to multiple states or allocated to states other than HQ
            non_home_states = [s for s in policy.state_allocated_taxes.keys() if s != policy.insured_hq_state]
            if len(non_home_states) > 0:
                allocated_non_home_amt = sum(policy.state_allocated_taxes[s] for s in non_home_states)
                lawful_home_tax = round((policy.premium + policy.carrier_fees) * tax_rate, 2)
                paid_to_home = policy.state_allocated_taxes.get(policy.insured_hq_state, 0.0)
                home_shortfall = max(0.0, round(lawful_home_tax - paid_to_home, 2))

                findings.append(
                    AuditFinding(
                        finding_id=f"{policy.policy_no}-F{finding_counter:02d}",
                        policy_no=policy.policy_no,
                        insured_name=policy.insured_name,
                        violation_type="INCORRECT_HOME_STATE_ALLOCATION",
                        state=policy.insured_hq_state,
                        statute_cite="15 U.S.C. § 8201 (NRRA / Dodd-Frank § 521)",
                        description=(
                            f"Multi-state premium tax allocation detected! Broker allocated ${allocated_non_home_amt:,.2f} "
                            f"across non-home states ({', '.join(non_home_states)}). Under NRRA § 521, ONLY the Home State "
                            f"({policy.insured_hq_state}) may tax the placement at 100% of gross premium."
                        ),
                        estimated_tax_at_risk=home_shortfall,
                        potential_penalty=round(home_shortfall * 0.10, 2),
                        total_financial_exposure=round(home_shortfall + (home_shortfall * 0.10), 2),
                        severity="CRITICAL",
                        remediation_path=(
                            f"File amended zero-returns and refund claims with unauthorized states ({', '.join(non_home_states)}) "
                            f"to recover ${allocated_non_home_amt:,.2f}. Remit true Home State shortfall of ${home_shortfall:,.2f} "
                            f"to {state_rule['state_name']} with NRRA single-state clarification schedule."
                        ),
                    )
                )
                finding_counter += 1

        return findings

    def run_policy_audit(self, policies: List[PolicyRecord]) -> Dict[str, Any]:
        all_findings: List[AuditFinding] = []
        summary = {
            "total_policies_audited": len(policies),
            "clean_policies": 0,
            "policies_with_findings": 0,
            "findings_by_type": {
                "UNREPORTED_CARRIER_FEE": 0,
                "LATE_FILING": 0,
                "UNCLAIMED_RETURN_PREMIUM": 0,
                "MISSING_ECP_DOCUMENTATION": 0,
                "INCORRECT_HOME_STATE_ALLOCATION": 0,
            },
            "total_tax_at_risk": 0.0,
            "total_penalties_at_risk": 0.0,
            "total_unclaimed_credits_recoverable": 0.0,
            "net_broker_exposure": 0.0,
            "findings": [],
        }

        for policy in policies:
            policy_findings = self.audit_policy(policy)
            if policy_findings:
                summary["policies_with_findings"] += 1
                for f in policy_findings:
                    summary["findings_by_type"][f.violation_type] = summary["findings_by_type"].get(f.violation_type, 0) + 1
                    if f.violation_type == "UNCLAIMED_RETURN_PREMIUM":
                        summary["total_unclaimed_credits_recoverable"] += f.total_financial_exposure
                    else:
                        summary["total_tax_at_risk"] += f.estimated_tax_at_risk
                        summary["total_penalties_at_risk"] += f.potential_penalty
                        summary["net_broker_exposure"] += f.total_financial_exposure
                all_findings.extend(policy_findings)
            else:
                summary["clean_policies"] += 1

        summary["total_tax_at_risk"] = round(summary["total_tax_at_risk"], 2)
        summary["total_penalties_at_risk"] = round(summary["total_penalties_at_risk"], 2)
        summary["total_unclaimed_credits_recoverable"] = round(summary["total_unclaimed_credits_recoverable"], 2)
        summary["net_broker_exposure"] = round(summary["net_broker_exposure"], 2)
        summary["findings"] = [f.to_dict() for f in all_findings]
        return summary

    def reconcile_stamping_vs_tax_return(
        self,
        stamping_records: List[StampingFilingItem],
        tax_return: AnnualTaxReturnSummary,
    ) -> ReconciliationReport:
        state_rule = self.get_state_rule(tax_return.state_code)
        tax_rate = state_rule["tax_rate"] / 100.0

        stamping_gross_prem = sum(item.gross_premium for item in stamping_records)
        stamping_carrier_fees = sum(item.carrier_fees for item in stamping_records)
        stamping_tax_base = stamping_gross_prem + stamping_carrier_fees

        prem_var = stamping_gross_prem - tax_return.reported_gross_premium
        fees_var = stamping_carrier_fees - tax_return.reported_carrier_fees
        net_base_var = stamping_tax_base - tax_return.reported_taxable_premium

        # Compare policy numbers
        stamped_policies_set = {item.policy_no for item in stamping_records}
        reported_policies_set = set(tax_return.reported_policies)

        unreported_stamped = sorted(list(stamped_policies_set - reported_policies_set))
        unstamped_reported = sorted(list(reported_policies_set - stamped_policies_set))

        # Check return premiums in stamping vs tax return
        stamped_return_premiums = sum(
            abs(item.gross_premium) for item in stamping_records if item.transaction_type == "CANCELLATION" or item.gross_premium < 0
        )
        unclaimed_return_credits = max(
            0.0,
            round((stamped_return_premiums * tax_rate) - tax_return.return_premium_credits_claimed, 2),
        )

        discrepancies: List[ReconciliationDiscrepancy] = []

        if abs(prem_var) > 1.0:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    discrepancy_type="GROSS_PREMIUM_VARIANCE",
                    identifier=f"PREM-{tax_return.state_code}-{tax_return.reporting_year}",
                    stamping_value=round(stamping_gross_prem, 2),
                    tax_return_value=round(tax_return.reported_gross_premium, 2),
                    variance=round(prem_var, 2),
                    statute_cite=state_rule["statutory_cite"],
                    explanation=(
                        f"Stamping office gross premium (${stamping_gross_prem:,.2f}) does not match "
                        f"annual tax return Form {tax_return.form_name} reported gross premium (${tax_return.reported_gross_premium:,.2f})."
                    ),
                    action_required="Reconcile itemized policy register and file amended annual tax schedule.",
                )
            )

        if abs(fees_var) > 1.0:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    discrepancy_type="CARRIER_FEE_OMISSION_VARIANCE",
                    identifier=f"FEES-{tax_return.state_code}-{tax_return.reporting_year}",
                    stamping_value=round(stamping_carrier_fees, 2),
                    tax_return_value=round(tax_return.reported_carrier_fees, 2),
                    variance=round(fees_var, 2),
                    statute_cite=state_rule["statutory_cite"],
                    explanation=(
                        f"Stamping records reflect ${stamping_carrier_fees:,.2f} in carrier/inspection fees, "
                        f"whereas tax return only reported ${tax_return.reported_carrier_fees:,.2f}. Carrier fees are taxable."
                    ),
                    action_required=f"Amend Form {tax_return.form_name} line item to include all carrier fees in taxable base.",
                )
            )

        for p_no in unreported_stamped:
            # Find item
            item = next(it for it in stamping_records if it.policy_no == p_no)
            tax_at_risk = round((item.gross_premium + item.carrier_fees) * tax_rate, 2)
            discrepancies.append(
                ReconciliationDiscrepancy(
                    discrepancy_type="UNREPORTED_TAX_RETURN_POLICY",
                    identifier=p_no,
                    stamping_value=round(item.gross_premium + item.carrier_fees, 2),
                    tax_return_value=0.0,
                    variance=round(item.gross_premium + item.carrier_fees, 2),
                    statute_cite=state_rule["statutory_cite"],
                    explanation=(
                        f"Policy {p_no} ({item.insured_name}) was successfully processed by {state_rule.get('stamping_office_name') or 'stamping office'}, "
                        f"but is completely absent from annual tax return Form {tax_return.form_name} schedule. Tax underpaid: ${tax_at_risk:,.2f}."
                    ),
                    action_required=f"Add policy {p_no} to amended annual tax return and remit shortfall.",
                )
            )

        for p_no in unstamped_reported:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    discrepancy_type="UNSTAMPED_REPORTED_POLICY",
                    identifier=p_no,
                    stamping_value=0.0,
                    tax_return_value=1.0,
                    variance=-1.0,
                    statute_cite=state_rule["statutory_cite"],
                    explanation=(
                        f"Policy {p_no} is reported on Form {tax_return.form_name}, but has NO corresponding "
                        f"filing record with {state_rule.get('stamping_office_name') or 'stamping office'}. Represents a statutory late/missing stamping violation."
                    ),
                    action_required=f"Submit policy documents to {state_rule.get('stamping_office_name') or 'stamping office'} immediately.",
                )
            )

        if unclaimed_return_credits > 1.0:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    discrepancy_type="UNCLAIMED_RETURN_PREMIUM_CREDIT",
                    identifier=f"RP-CREDIT-{tax_return.state_code}",
                    stamping_value=round(stamped_return_premiums * tax_rate, 2),
                    tax_return_value=round(tax_return.return_premium_credits_claimed, 2),
                    variance=round(unclaimed_return_credits, 2),
                    statute_cite=state_rule["statutory_cite"],
                    explanation=(
                        f"Broker is entitled to ${unclaimed_return_credits:,.2f} in return-premium tax credits stamped by "
                        f"stamping office but not claimed on annual tax return Form {tax_return.form_name}."
                    ),
                    action_required=f"Claim ${unclaimed_return_credits:,.2f} tax credit on amended return or request refund check.",
                )
            )

        est_shortfall = round(net_base_var * tax_rate, 2)

        return ReconciliationReport(
            state_code=tax_return.state_code,
            reporting_year=tax_return.reporting_year,
            form_name=tax_return.form_name,
            stamping_total_policies=len(stamping_records),
            tax_return_total_policies=len(tax_return.reported_policies),
            stamping_gross_premium=stamping_gross_prem,
            tax_return_gross_premium=tax_return.reported_gross_premium,
            premium_variance=prem_var,
            stamping_carrier_fees=stamping_carrier_fees,
            tax_return_carrier_fees=tax_return.reported_carrier_fees,
            carrier_fees_variance=fees_var,
            stamping_total_tax_base=stamping_tax_base,
            tax_return_tax_base=tax_return.reported_taxable_premium,
            net_tax_base_variance=net_base_var,
            estimated_tax_shortfall_or_credit=est_shortfall,
            unreported_stamped_policies=unreported_stamped,
            unstamped_reported_policies=unstamped_reported,
            unclaimed_return_premium_credits=unclaimed_return_credits,
            discrepancies=discrepancies,
        )


def load_policies_from_csv(csv_path: Path) -> List[PolicyRecord]:
    policies: List[PolicyRecord] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            policies.append(PolicyRecord.from_dict(row))
    return policies


def load_stamping_filings_from_csv(csv_path: Path) -> List[StampingFilingItem]:
    items: List[StampingFilingItem] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(StampingFilingItem.from_dict(row))
    return items


def main():
    import argparse

    parser = argparse.ArgumentParser(description="E&S Premium Tax Audit & Reconciliation Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Audit broker policies CSV")
    audit_parser.add_argument("--csv", required=True, help="Path to broker policy export CSV")
    audit_parser.add_argument("--out", help="Optional JSON output path")

    reconcile_parser = subparsers.add_parser("reconcile", help="Reconcile stamping extract vs tax return")
    reconcile_parser.add_argument("--stamping-csv", required=True, help="Path to stamping extract CSV (SLTX/ELANY/SLIP)")
    reconcile_parser.add_argument("--tax-return-json", required=True, help="Path to tax return summary JSON (FIN317/11-13)")
    reconcile_parser.add_argument("--out", help="Optional JSON output path")

    args = parser.parse_args()
    engine = PremiumTaxRulesEngine()

    if args.command == "audit":
        policies = load_policies_from_csv(Path(args.csv))
        result = engine.run_policy_audit(policies)
        print(f"=== AUDIT COMPLETE: {result['total_policies_audited']} Policies Audited ===")
        print(f"Clean Policies: {result['clean_policies']} | Flagged: {result['policies_with_findings']}")
        print(f"Tax At Risk: ${result['total_tax_at_risk']:,.2f}")
        print(f"Penalties At Risk: ${result['total_penalties_at_risk']:,.2f}")
        print(f"Unclaimed Recoverable Credits: ${result['total_unclaimed_credits_recoverable']:,.2f}")
        print(f"Net Broker Financial Exposure: ${result['net_broker_exposure']:,.2f}")
        print(f"Findings Breakdown: {result['findings_by_type']}")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"Report saved to {args.out}")

    elif args.command == "reconcile":
        stamping_records = load_stamping_filings_from_csv(Path(args.stamping_csv))
        with open(args.tax_return_json, "r", encoding="utf-8") as f:
            tax_dict = json.load(f)
        tax_return = AnnualTaxReturnSummary(**tax_dict)
        report = engine.reconcile_stamping_vs_tax_return(stamping_records, tax_return)
        print(f"=== RECONCILIATION COMPLETE: {tax_return.state_code} {tax_return.reporting_year} Form {tax_return.form_name} ===")
        print(f"Stamping Premium: ${report.stamping_gross_premium:,.2f} vs Tax Return: ${report.tax_return_gross_premium:,.2f} (Variance: ${report.premium_variance:,.2f})")
        print(f"Carrier Fees Variance: ${report.carrier_fees_variance:,.2f}")
        print(f"Net Tax Base Variance: ${report.net_tax_base_variance:,.2f}")
        print(f"Discrepancies Identified: {len(report.discrepancies)}")
        print(f"Unclaimed Return Credits: ${report.unclaimed_return_premium_credits:,.2f}")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"Reconciliation report saved to {args.out}")


if __name__ == "__main__":
    main()
