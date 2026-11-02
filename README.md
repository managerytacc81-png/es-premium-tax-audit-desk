# E&S Premium-Tax Audit Desk (`es-premium-tax-audit-desk`)
**Forensic Rules Engine, Stamping Reconciliation & Commercial Lead Harvester for US Surplus Lines Wholesale Brokerages**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/pytest-16%20passed%20%28100%25%29-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Regulatory Base](https://img.shields.io/badge/NRRA-Dodd--Frank%20%C2%A7521-navy.svg)]()

---

## 1. Executive Summary & Market Context

The United States Excess and Surplus Lines (E&S) insurance market accounted for **$90.3 Billion in annual premium** reported through 15 state stamping offices in 2025 (WSIA Annual Statistical Report)—representing over 12% of the entire domestic Property & Casualty commercial insurance sector.

Under the **Nonadmitted and Reinsurance Reform Act of 2010 (NRRA / Dodd-Frank § 521, 15 U.S.C. §§ 8201–8206)**, the statutory taxing authority for non-admitted placements is strictly preempted: **ONLY the insured's "Home State" possesses the legal jurisdiction to levy premium taxes**, regardless of where underlying property or operational risks reside. 

Across the 50 states and Washington D.C., state surplus lines premium tax rates fluctuate between **0.925% (Iowa)** and **6.00% (Alabama, Oklahoma, South Carolina)**. In addition, the **15 states with dedicated stamping and service offices** (AZ, CA, FL, ID, IL, MN, MS, NV, NY, NC, OR, PA, TX, UT, WA) assess statutory stamping/transaction fees ranging from **0.04% to 0.50%**. Together, wholesale brokers collect and remit over **$3.5 Billion annually** in state surplus lines tax and stamping assessments.

```
       +-------------------------------------------------------------+
       |               Broker Policy Placement / Binding             |
       +-------------------------------------------------------------+
                                      |
         +----------------------------+----------------------------+
         |                                                         |
         v                                                         v
+-------------------------------+                       +-------------------------------+
|  15 Stamping Offices (SLTX,   |                       |   State Tax Return Filings    |
|  ELANY, FSLSO, SLAI, SLA CA)  |                       |  (TX FIN317, NY 11-13, CA-1)  |
+-------------------------------+                       +-------------------------------+
         |                                                         |
         +----------------------------+----------------------------+
                                      |
                                      v
                 +-----------------------------------------+
                 |    E&S Premium-Tax Audit Engine         |
                 |  - Line-by-Line Stamping Reconciliation |
                 |  - Carrier/Inspection Fee Sweep         |
                 |  - Filing Deadline Enforcement Matrix   |
                 |  - Return-Premium Credit Sweep          |
                 |  - NRRA Single Home-State Validation    |
                 |  - ECP Exemption Affidavit Audit        |
                 +-----------------------------------------+
                                      |
         +----------------------------+----------------------------+
         |                                                         |
         v                                                         v
+-------------------------------+                       +-------------------------------+
|   Statutory Defense Binder    |                       |   Direct Cash Recovery        |
|  (Cure Shortfalls & Defend    |                       |  (Unclaimed Return-Premium    |
|   Market Conduct DOI Audits)  |                       |   Tax Credits & Cash Refunds) |
+-------------------------------+                       +-------------------------------+
```

---

## 2. Enforcement Precedents & Regulatory Liability

State Departments of Insurance (DOIs) have shifted to automated forensic cross-matching between stamping office policy transaction logs and broker annual/quarterly tax returns. Penalties are unsuspended, public, and substantial:

* **Alaska DOI Order D25-09 (Aon Risk Services, June 2025):** 216 compliance and fee violations resulted in a **$60,000 regulatory civil penalty** for omitting carrier/inspection charges from taxable premium and late policy clearing.
* **Alaska DOI Order D15-11 (Marsh USA):** 157 policy clearing violations resulted in a **$50,000 civil fine**.
* **Alaska DOI Order D15-13:** 29 surplus lines logging failures triggered an immediate **$30,000 unsuspended penalty**.
* **Texas Insurance Code § 981.008 & 28 TAC § 15.101:** Mandates inclusion of all carrier fees, policy fees, and inspection fees into taxable gross premium; late filings with SLTX (>60 days) trigger administrative penalties and referral to the Comptroller.

### Common Market Conduct Audit Traps:
1. **Unreported Carrier & Inspection Fees:** Wholesalers frequently tax only the pure carrier base premium, omitting inspection fees, policy fees, and carrier pass-through charges. Under state bulletins (e.g., AK Bulletin 04-14, TIC § 981.008, Cal. Ins. Code § 1765.2, Fla. Stat. § 626.932), this constitutes statutory underpayment of premium tax.
2. **Missed Statutory Filing Deadlines:** Stamping jurisdictions require prompt submission (CA: 30 days, FL: 30 days, IL: 30 days, NY: 45 days, TX: 60 days). Late filings trigger cumulative monthly late fines.
3. **Unclaimed Return-Premium Credits:** In states like Georgia (O.C.G.A. § 33-5-31: credit-only against future filings, zero cash refunds), Alabama (Ala. Code § 27-10-31: requires amended Form ID-15), and South Carolina (S.C. Code § 38-45-60: negative endorsement schedule), brokers forfeit tens of thousands in unearned premium tax credits if not actively reconciled.
4. **Defective Exempt Commercial Purchaser (ECP) Documentation:** Diligent search exemptions under NRRA (15 U.S.C. § 8206) and state statutes (e.g., TIC § 981.0031) require verified, signed affidavits on file confirming the insured employs a qualified risk manager and exceeds $100k nationwide premium + $20M net worth or $50M revenue.

---

## 3. Product Architecture & Modules

The repository delivers a complete, modular audit desk:

```
es-premium-tax-audit-desk/
├── rules_db/
│   └── states.json             # Exhaustive rules for all 50 states + DC
├── audit_checks.py             # Core rules engine & SLTX/FIN317 reconciliation
├── lead_scraper.py             # Texas Socrata API harvester & deduplicator
├── build_rules_db.py           # Automated schema validator & builder
├── generate_outbox.py          # Commercial outbox & 1-click SMTP script generator
├── fixtures/
│   ├── sample_broker_export.csv
│   ├── sample_stamping_extract.csv
│   └── sample_fin317_return.json
├── tests/
│   ├── conftest.py
│   └── test_es_audit.py        # 16 comprehensive pytest test cases
└── README.md
```

### 1. `rules_db/states.json`
Encodes all 50 US States + DC with statutory citations:
- **Tax Rates:** Exact statutory rates (from 0.925% in IA to 6.0% in AL/OK/SC).
- **15 Stamping Offices:** Flag, legal association name, and exact stamping fee % (e.g., TX SLTX 0.04%, CA SLA 0.25%, FL FSLSO 0.06%, NY ELANY 0.15%, IL SLAI 0.04%).
- **Statutory Deadlines:** Strict calendar clearing window (days post-effective).
- **Return-Premium Mechanics:** Explicit categorization (`cash-refund`, `credit-only`, `amended-return`, `negative-endorsement`, `annual-reconciliation`).
- **ECP Safe Harbor:** State statutory citations and criteria.
- **Direct Procurement:** Independent procurement tax rates and deadlines (SurplusManual Appendix B).
- **Primary Statutory Citations & Sources:** Three-way validation citing NAIC Model Law Chart ZZ-7, WSIA Tax Filing Procedures Chart, and SurplusManual.com.

### 2. `audit_checks.py`
Ingests broker policy CSV exports and executes 5 audit checks:
* `UNREPORTED_CARRIER_FEE`: Computes underpaid tax, stamping fee shortfall, and 10% statutory penalty.
* `LATE_FILING`: Evaluates elapsed clearing days vs statutory deadlines and estimates penalty exposure.
* `UNCLAIMED_RETURN_PREMIUM`: Sweeps negative endorsements and calculates direct cash recovery / tax credits.
* `MISSING_ECP_DOCUMENTATION`: Identifies unverified commercial purchaser exemptions subject to regulatory invalidation.
* `INCORRECT_HOME_STATE_ALLOCATION`: Flags illegal multi-state premium tax allocations under NRRA § 521.

#### Line-by-Line Stamping vs. Tax Return Reconciliation Module:
Compares monthly/quarterly stamping office extracts (SLTX, ELANY, FSLSO SLIP) against broker annual tax return filings (Comptroller Form FIN317, NY Form 11-13, CA TAX-1):
- Detects gross premium discrepancies.
- Detects omitted carrier/inspection fees.
- Identifies unfiled stamped policies (unreported on tax return).
- Identifies unstamped policies (reported on tax return without stamping office record).
- Flags unclaimed return-premium tax credits.

### 3. `lead_scraper.py`
Harvester connecting directly to the State of Texas Open Data Portal (`data.texas.gov` Socrata endpoints):
- **Dataset `3yqc-fcdt`:** Insurance agencies approved to transact surplus lines (city, state, postal code, NPN).
- **Dataset `7isd-ex6t`:** TDI surplus lines active firm licensing status.
- **Dataset `ghh2-6wm5`:** Active corporate officers, directors, and principals.
- Filters out national enterprise mega-brokers (Aon, Marsh, Gallagher, Amwins, Hub, RT Specialty, CRC, Lockton) to focus exclusively on sub-Big-4 regional wholesale brokerages and MGAs in the 15 stamping states.

---

## 4. Quick Start & CLI Usage

### Running Policy Audits
```bash
# Run forensic audit on broker policy export
python3 audit_checks.py audit --csv fixtures/sample_broker_export.csv --out audit_findings.json
```

**Sample Output:**
```text
=== AUDIT COMPLETE: 7 Policies Audited ===
Clean Policies: 1 | Flagged: 6
Tax At Risk: $34,837.50
Penalties At Risk: $5,505.62
Unclaimed Recoverable Credits: $1,400.00
Net Broker Financial Exposure: $40,343.12
Findings Breakdown: {'UNREPORTED_CARRIER_FEE': 2, 'LATE_FILING': 2, 'UNCLAIMED_RETURN_PREMIUM': 1, 'MISSING_ECP_DOCUMENTATION': 1, 'INCORRECT_HOME_STATE_ALLOCATION': 1}
```

### Running Stamping Office vs Tax Return Reconciliation
```bash
# Reconcile SLTX / ELANY stamping extract vs Comptroller Form FIN317
python3 audit_checks.py reconcile \
  --stamping-csv fixtures/sample_stamping_extract.csv \
  --tax-return-json fixtures/sample_fin317_return.json \
  --out reconciliation_report.json
```

**Sample Output:**
```text
=== RECONCILIATION COMPLETE: TX 2025 Form FIN317 ===
Stamping Premium: $1,130,000.00 vs Tax Return: $1,170,000.00 (Variance: $-40,000.00)
Carrier Fees Variance: $17,500.00
Net Tax Base Variance: $-22,500.00
Discrepancies Identified: 4
Unclaimed Return Credits: $1,940.00
```

### Scraping Texas Open Data Portal Leads
```bash
# Harvester: pull active surplus lines agencies in the 15 stamping states
python3 lead_scraper.py --output leads.csv --stamping-only
```

---

## 5. Test Suite Verification

Run the comprehensive pytest suite verifying database integrity, statutory rules, audit logic, reconciliation math, and lead parsing:

```bash
pytest tests/test_es_audit.py -v
```

```text
======================== 16 passed, 1 warning in 0.07s =========================
```

---

## 6. Commercial Service Offerings

| Service Package | Target Client | Scope of Delivery | Fixed Fee |
| :--- | :--- | :--- | :--- |
| **Single-State Pre-Audit Health-Check** | Regional Wholesale Broker / MGA | Full stamping vs. tax return line-by-line reconciliation (1 state, e.g. TX SLTX or CA SLA); carrier fee sweep; return-premium recovery audit; ECP defense binder. | **$3,500** *(3-Day Turnaround)* |
| **4-State Regional Audit Health-Check** | Multi-State Regional Wholesaler | Comprehensive 4-jurisdiction forensic audit across primary stamping footprints (e.g. TX, CA, FL, IL); cross-state NRRA § 521 allocation review. | **$8,500** *(5-Day Turnaround)* |
| **Quarterly Watch Desk Retainer** | Active E&S Program Administrator | Ongoing quarterly pre-flown stamping reconciliation, statutory rules-change monitoring, and continuous return-premium credit sweeps. | **$500 – $900 / month** |

---

## 7. Regulatory Disclaimer

> [!IMPORTANT]
> **Regulatory Notice & Statutory Disclaimer:**  
> The software, databases, calculations, and materials contained in this repository are developed strictly for informational compliance research, internal quality control, and automated forensic data reconciliation. This toolkit does not constitute formal legal representation, legal advice, or a certified public accounting (CPA) tax opinion. Surplus lines licensing, tax calculation, and regulatory filings are governed by state-specific insurance departments, statutes, administrative codes, and the federal Nonadmitted and Reinsurance Reform Act (NRRA). Users must consult qualified insurance regulatory counsel or licensed tax professionals before submitting amended tax schedules, refund petitions, or formal administrative safe-harbor self-disclosures.

---
*Developed under the Maximum Autonomous AI Execution Protocol for the US Surplus Lines Wholesale Brokerage Sector.*
