#!/usr/bin/env python3
"""
Test suite for E&S Premium-Tax Audit Desk
Verifies rules engine, audit checks, reconciliation, and lead scraping.
"""

import json
import pytest
from pathlib import Path

from audit_checks import (
    AnnualTaxReturnSummary,
    AuditFinding,
    PolicyRecord,
    PremiumTaxRulesEngine,
    ReconciliationReport,
    StampingFilingItem,
)
from lead_scraper import NATIONAL_MEGA_BROKERS, STAMPING_STATES, SurplusLinesLead, is_national_brand


@pytest.fixture
def rules_engine():
    states_path = Path(__file__).resolve().parent.parent / "rules_db" / "states.json"
    return PremiumTaxRulesEngine(states_path)


# ============================================================================
# 1. RULES DATABASE INTEGRITY TESTS (50 States + DC)
# ============================================================================

def test_states_db_count_and_keys(rules_engine):
    db = rules_engine.states_db
    assert len(db) == 51, f"Expected 51 jurisdictions, got {len(db)}"
    
    required_keys = {
        "state_code", "state_name", "tax_rate", "stamping_office",
        "stamping_office_name", "stamping_fee_pct", "filing_deadline_days",
        "tax_periodicity", "tax_due_dates", "return_premium_credit_mechanics",
        "return_premium_details", "ecp_accepted", "ecp_statutory_cite",
        "ecp_criteria", "direct_procurement_tax_rate", "direct_procurement_rule",
        "statutory_cite", "sources"
    }

    for state, data in db.items():
        missing = required_keys - set(data.keys())
        assert not missing, f"State {state} is missing keys: {missing}"
        assert len(state) == 2, f"Invalid state code: {state}"
        assert data["tax_rate"] >= 0.925 and data["tax_rate"] <= 6.0
        assert data["filing_deadline_days"] in (20, 30, 45, 60)
        assert data["ecp_accepted"] is True
        assert len(data["sources"]) == 3
        assert "naic_chart_zz7" in data["sources"]
        assert "wsia_chart" in data["sources"]
        assert "surplus_manual_app_b" in data["sources"]


def test_fifteen_stamping_states_exact(rules_engine):
    db = rules_engine.states_db
    stamping_states = {s for s, d in db.items() if d["stamping_office"]}
    expected_15 = {"AZ", "CA", "FL", "ID", "IL", "MN", "MS", "NV", "NY", "NC", "OR", "PA", "TX", "UT", "WA"}
    
    assert stamping_states == expected_15, f"Stamping states mismatch: {stamping_states ^ expected_15}"
    assert stamping_states == STAMPING_STATES

    for state in stamping_states:
        d = db[state]
        assert d["stamping_fee_pct"] > 0.0, f"{state} stamping fee should be > 0"
        assert d["stamping_office_name"] is not None and len(d["stamping_office_name"]) > 5

    non_stamping = set(db.keys()) - stamping_states
    for state in non_stamping:
        d = db[state]
        assert d["stamping_fee_pct"] == 0.0
        assert d["stamping_office_name"] is None


def test_specific_state_mechanics(rules_engine):
    db = rules_engine.states_db

    # Texas
    tx = db["TX"]
    assert tx["tax_rate"] == 4.85
    assert tx["stamping_fee_pct"] == 0.04
    assert tx["filing_deadline_days"] == 60
    assert tx["return_premium_credit_mechanics"] == "annual-reconciliation"
    assert "981.0031" in tx["ecp_statutory_cite"]

    # California
    ca = db["CA"]
    assert ca["tax_rate"] == 3.0
    assert ca["stamping_fee_pct"] == 0.25
    assert ca["filing_deadline_days"] == 30

    # New York ELANY
    ny = db["NY"]
    assert ny["tax_rate"] == 3.6
    assert ny["stamping_fee_pct"] == 0.15
    assert ny["filing_deadline_days"] == 45
    assert "ELANY" in ny["stamping_office_name"]

    # Georgia: Credit-only
    ga = db["GA"]
    assert ga["return_premium_credit_mechanics"] == "credit-only"
    assert "cash refund" in ga["return_premium_details"].lower()

    # Alabama: Amended ID-15
    al = db["AL"]
    assert al["tax_rate"] == 6.0
    assert al["return_premium_credit_mechanics"] == "amended-return"
    assert "ID-15" in al["return_premium_details"]

    # South Carolina: Negative Endorsement
    sc = db["SC"]
    assert sc["tax_rate"] == 6.0
    assert sc["return_premium_credit_mechanics"] == "negative-endorsement"

    # Iowa: Lowest US rate
    ia = db["IA"]
    assert ia["tax_rate"] == 0.925


# ============================================================================
# 2. AUDIT CHECKS LOGIC TESTS
# ============================================================================

def test_unreported_carrier_fee_detection(rules_engine):
    # Texas policy with $10,000 carrier fees untaxed
    policy = PolicyRecord(
        policy_no="POL-TX-001",
        insured_name="Lone Star Energy LLC",
        insured_hq_state="TX",
        risk_states=["TX"],
        premium=100000.0,
        carrier_fees=10000.0,
        effective_date="2026-01-01",
        filed_date="2026-01-20",
        carrier_fee_taxed=False,
    )

    findings = rules_engine.audit_policy(policy)
    fee_findings = [f for f in findings if f.violation_type == "UNREPORTED_CARRIER_FEE"]
    assert len(fee_findings) == 1
    f = fee_findings[0]
    # Tax at risk = $10,000 * 4.85% = $485 tax + 0.04% stamping = $4 -> $489
    expected_tax = round(10000.0 * 0.0485 + 10000.0 * 0.0004, 2)
    assert f.estimated_tax_at_risk == expected_tax
    assert f.potential_penalty == round(485.0 * 0.10, 2)
    assert f.severity == "HIGH"
    assert "TIC § 981.008" in f.statute_cite or "225.004" in f.statute_cite


def test_carrier_fee_taxed_produces_no_finding(rules_engine):
    policy = PolicyRecord(
        policy_no="POL-TX-002",
        insured_name="Lone Star Energy LLC",
        insured_hq_state="TX",
        risk_states=["TX"],
        premium=100000.0,
        carrier_fees=10000.0,
        effective_date="2026-01-01",
        filed_date="2026-01-20",
        carrier_fee_taxed=True,  # properly taxed
    )

    findings = rules_engine.audit_policy(policy)
    fee_findings = [f for f in findings if f.violation_type == "UNREPORTED_CARRIER_FEE"]
    assert len(fee_findings) == 0


def test_late_filing_detection(rules_engine):
    # California policy (30d limit), filed at 55 days
    policy = PolicyRecord(
        policy_no="POL-CA-001",
        insured_name="Pacific Tech Corp",
        insured_hq_state="CA",
        risk_states=["CA"],
        premium=50000.0,
        effective_date="2026-01-01",
        filed_date="2026-02-25",  # 55 days later (25 days overdue)
    )

    findings = rules_engine.audit_policy(policy)
    late_findings = [f for f in findings if f.violation_type == "LATE_FILING"]
    assert len(late_findings) == 1
    f = late_findings[0]
    assert "Exceeded statutory deadline by 25 days" in f.description
    assert f.potential_penalty > 0


def test_on_time_filing_produces_no_late_finding(rules_engine):
    # Texas policy (60d limit), filed at 40 days
    policy = PolicyRecord(
        policy_no="POL-TX-003",
        insured_name="Dallas Logistics Inc",
        insured_hq_state="TX",
        risk_states=["TX"],
        premium=50000.0,
        effective_date="2026-01-01",
        filed_date="2026-02-10",  # 40 days
    )

    findings = rules_engine.audit_policy(policy)
    late_findings = [f for f in findings if f.violation_type == "LATE_FILING"]
    assert len(late_findings) == 0


def test_unclaimed_return_premium_credit_sweep(rules_engine):
    # Georgia policy with $25,000 returned premium
    policy = PolicyRecord(
        policy_no="POL-GA-001",
        insured_name="Peach State Manufacturing",
        insured_hq_state="GA",
        risk_states=["GA"],
        premium=100000.0,
        effective_date="2026-01-01",
        filed_date="2026-01-15",
        cancellations_returns=-25000.0,
    )

    findings = rules_engine.audit_policy(policy)
    rp_findings = [f for f in findings if f.violation_type == "UNCLAIMED_RETURN_PREMIUM"]
    assert len(rp_findings) == 1
    f = rp_findings[0]
    # GA tax rate = 4.0% of $25,000 = $1,000
    assert f.total_financial_exposure == 1000.0
    assert f.severity == "OPPORTUNITY_CREDIT"
    assert "credit-only" in f.description
    assert "no cash refund" in f.description.lower() or "offset" in f.remediation_path.lower()


def test_missing_ecp_documentation_detection(rules_engine):
    # Policy marked ECP but ecp_documented is False
    policy = PolicyRecord(
        policy_no="POL-TX-ECP",
        insured_name="Global Energy Holdings",
        insured_hq_state="TX",
        risk_states=["TX"],
        premium=250000.0,
        effective_date="2026-01-01",
        filed_date="2026-01-20",
        ecp_flag=True,
        ecp_documented=False,
    )

    findings = rules_engine.audit_policy(policy)
    ecp_findings = [f for f in findings if f.violation_type == "MISSING_ECP_DOCUMENTATION"]
    assert len(ecp_findings) == 1
    f = ecp_findings[0]
    assert f.severity == "CRITICAL"
    assert "15 U.S.C. § 8206" in f.statute_cite or "981.0031" in f.statute_cite
    assert f.estimated_tax_at_risk == round(250000.0 * 0.0485, 2)


def test_ecp_documented_produces_no_finding(rules_engine):
    policy = PolicyRecord(
        policy_no="POL-TX-ECP-OK",
        insured_name="Global Energy Holdings",
        insured_hq_state="TX",
        risk_states=["TX"],
        premium=250000.0,
        effective_date="2026-01-01",
        filed_date="2026-01-20",
        ecp_flag=True,
        ecp_documented=True,  # verified documentation on file
    )

    findings = rules_engine.audit_policy(policy)
    ecp_findings = [f for f in findings if f.violation_type == "MISSING_ECP_DOCUMENTATION"]
    assert len(ecp_findings) == 0


def test_nrra_home_state_allocation_violation(rules_engine):
    # Broker allocated taxes across TX (HQ), CA, and FL
    policy = PolicyRecord(
        policy_no="POL-MULTI-001",
        insured_name="Multi-State Retailer Inc",
        insured_hq_state="TX",
        risk_states=["TX", "CA", "FL"],
        premium=100000.0,
        effective_date="2026-01-01",
        filed_date="2026-01-20",
        state_allocated_taxes={"TX": 2000.0, "CA": 1500.0, "FL": 1350.0},
    )

    findings = rules_engine.audit_policy(policy)
    nrra_findings = [f for f in findings if f.violation_type == "INCORRECT_HOME_STATE_ALLOCATION"]
    assert len(nrra_findings) == 1
    f = nrra_findings[0]
    assert f.severity == "CRITICAL"
    assert "15 U.S.C. § 8201" in f.statute_cite
    assert "CA, FL" in f.description or "FL, CA" in f.description
    # Lawful TX tax is $4,850, broker only paid $2,000 to TX -> shortfall is $2,850
    assert f.estimated_tax_at_risk == 2850.0


def test_clean_compliant_policy(rules_engine):
    policy = PolicyRecord(
        policy_no="POL-CLEAN-001",
        insured_name="Compliant Holdings LLC",
        insured_hq_state="TX",
        risk_states=["TX"],
        premium=100000.0,
        carrier_fees=0.0,
        effective_date="2026-01-01",
        filed_date="2026-01-15",
        cancellations_returns=0.0,
        ecp_flag=False,
    )

    findings = rules_engine.audit_policy(policy)
    assert len(findings) == 0


def test_batch_run_policy_audit(rules_engine):
    policies = [
        # Clean policy
        PolicyRecord("P1", "Clean Co", "TX", ["TX"], 100000.0, effective_date="2026-01-01", filed_date="2026-01-15"),
        # Carrier fee violation
        PolicyRecord("P2", "Fee Co", "TX", ["TX"], 100000.0, carrier_fees=5000.0, effective_date="2026-01-01", filed_date="2026-01-15"),
        # Late policy
        PolicyRecord("P3", "Late Co", "CA", ["CA"], 50000.0, effective_date="2026-01-01", filed_date="2026-03-01"),
        # Return premium credit opportunity
        PolicyRecord("P4", "Return Co", "GA", ["GA"], 80000.0, effective_date="2026-01-01", filed_date="2026-01-15", cancellations_returns=-10000.0),
    ]

    res = rules_engine.run_policy_audit(policies)
    assert res["total_policies_audited"] == 4
    assert res["clean_policies"] == 1
    assert res["policies_with_findings"] == 3
    assert res["findings_by_type"]["UNREPORTED_CARRIER_FEE"] == 1
    assert res["findings_by_type"]["LATE_FILING"] == 1
    assert res["findings_by_type"]["UNCLAIMED_RETURN_PREMIUM"] == 1
    assert res["total_unclaimed_credits_recoverable"] == 400.0  # 4% of $10k in GA


# ============================================================================
# 3. RECONCILIATION MODULE TESTS (Stamping vs Tax Return FIN317)
# ============================================================================

def test_stamping_vs_tax_return_reconciliation(rules_engine):
    # Stamping office records for Texas (SLTX)
    stamping_records = [
        StampingFilingItem(
            filing_id="STAMP-001",
            policy_no="POL-101",
            insured_name="Austin Energy Corp",
            transaction_type="NEW",
            effective_date="2025-01-15",
            stamped_date="2025-02-10",
            gross_premium=500000.0,
            carrier_fees=15000.0,
            stamping_fee=206.0,
            calculated_tax=24977.5,
        ),
        StampingFilingItem(
            filing_id="STAMP-002",
            policy_no="POL-102",
            insured_name="San Antonio Logistics",
            transaction_type="NEW",
            effective_date="2025-03-01",
            stamped_date="2025-03-20",
            gross_premium=300000.0,
            carrier_fees=5000.0,
            stamping_fee=122.0,
            calculated_tax=14792.5,
        ),
        StampingFilingItem(
            filing_id="STAMP-003",
            policy_no="POL-103",
            insured_name="Houston Offshore Services",
            transaction_type="CANCELLATION",
            effective_date="2025-06-01",
            stamped_date="2025-06-15",
            gross_premium=-50000.0,
            carrier_fees=0.0,
            stamping_fee=-20.0,
            calculated_tax=-2425.0,
        ),
    ]

    # Broker annual tax return Form FIN317:
    # Notice: Broker omitted carrier fees ($20,000 total) and failed to claim the return premium credit ($2,425)
    tax_return = AnnualTaxReturnSummary(
        state_code="TX",
        reporting_year=2025,
        form_name="FIN317",
        reported_gross_premium=800000.0,
        reported_carrier_fees=0.0,  # omitted $20,000 in carrier fees!
        reported_taxable_premium=800000.0,
        tax_rate=4.85,
        total_tax_liability=38800.0,
        prepayments_credited=10000.0,
        return_premium_credits_claimed=0.0,  # unclaimed!
        net_tax_paid=28800.0,
        reported_policies=["POL-101", "POL-102"],  # omitted POL-103
    )

    report = rules_engine.reconcile_stamping_vs_tax_return(stamping_records, tax_return)

    assert report.state_code == "TX"
    assert report.reporting_year == 2025
    assert report.form_name == "FIN317"
    assert report.carrier_fees_variance == 20000.0
    assert report.unclaimed_return_premium_credits == 2425.0
    assert "POL-103" in report.unreported_stamped_policies

    # Verify discrepancies logged
    disc_types = [d.discrepancy_type for d in report.discrepancies]
    assert "CARRIER_FEE_OMISSION_VARIANCE" in disc_types
    assert "UNREPORTED_TAX_RETURN_POLICY" in disc_types
    assert "UNCLAIMED_RETURN_PREMIUM_CREDIT" in disc_types


# ============================================================================
# 4. LEAD SCRAPER & FILTERING TESTS
# ============================================================================

def test_national_brand_filter():
    assert is_national_brand("AON RISK SERVICES SOUTHWEST INC") is True
    assert is_national_brand("MARSH USA INC") is True
    assert is_national_brand("ARTHUR J GALLAGHER & CO") is True
    assert is_national_brand("AMWINS BROKERAGE OF TEXAS") is True
    assert is_national_brand("HUB INTERNATIONAL TEXAS INC") is True
    assert is_national_brand("RT SPECIALTY LLC") is True
    assert is_national_brand("CRC INSURANCE SERVICES INC") is True

    # Regional wholesale brokers should NOT be excluded
    assert is_national_brand("FREDERIKSEN & FREDERIKSEN A CORP") is False
    assert is_national_brand("BRAZOS SPECIALTY RISK LLC") is False
    assert is_national_brand("AMERICAN RISK SERVICES LLC") is False
    assert is_national_brand("SOUTHWEST RISK LP") is False


def test_surplus_lines_lead_structure():
    lead = SurplusLinesLead(
        company="TEXAS REGIONAL UNDERWRITERS LLC",
        city="DALLAS",
        state="TX",
        license_id="1234567",
        zip_code="75201",
        npn="98765432",
        officer_name="JOHN DOE",
        stamping_state=True,
    )
    d = lead.to_dict()
    assert d["company"] == "TEXAS REGIONAL UNDERWRITERS LLC"
    assert d["state"] == "TX"
    assert d["stamping_state"] == "YES"
    assert d["officer_name"] == "JOHN DOE"
