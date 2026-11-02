#!/usr/bin/env python3
"""
Texas Socrata Surplus Lines Licensee Scraper & Lead Harvester
(slug: es-premium-tax-audit-desk)

Pulls active surplus lines entities from the State of Texas Open Data Portal (data.texas.gov):
- Dataset 7isd-ex6t: Surplus lines agent and agency status detail
- Dataset 3yqc-fcdt: Insurance agencies and businesses approved to manage insurance-related products
- Dataset ghh2-6wm5: Active officers and directors for active surplus lines agencies

Filters to entity business-type licensees with active status, joins city/state and executive officers,
deduplicates on license ID, and exports leads.csv.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

# 15 States with independent surplus lines stamping offices
STAMPING_STATES = {
    "AZ", "CA", "FL", "ID", "IL", "MN", "MS", "NV", "NY", "NC", "OR", "PA", "TX", "UT", "WA"
}

# Mega-broker national brands excluded from sub-Big-4 regional wholesale campaign
NATIONAL_MEGA_BROKERS = {
    "AON", "MARSH", "GALLAGHER", "AMWINS", "HUB INTERNATIONAL",
    "RT SPECIALTY", "RYAN SPECIALTY", "CRC INSURANCE", "CRC GROUP",
    "WILLIS TOWERS WATSON", "WTW", "BROWN & BROWN", "USI INSURANCE",
    "ALLIANT", "LOCKTON", "ACRISURE", "RISK PLACEMENT SERVICES", "RPS"
}


@dataclass
class SurplusLinesLead:
    company: str
    city: str
    state: str
    license_id: str
    zip_code: str = ""
    npn: str = ""
    officer_name: str = ""
    stamping_state: bool = False

    def to_dict(self) -> Dict[str, str]:
        return {
            "company": self.company,
            "city": self.city,
            "state": self.state,
            "license_id": self.license_id,
            "zip_code": self.zip_code,
            "npn": self.npn,
            "officer_name": self.officer_name,
            "stamping_state": "YES" if self.stamping_state else "NO",
        }


def fetch_socrata_csv(url: str, timeout: int = 30) -> List[Dict[str, str]]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ES-Premium-Tax-Audit-Desk/1.0 (Compliance Forensic Engine; research@es-audit.org)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def is_national_brand(company_name: str) -> bool:
    name_upper = company_name.upper()
    for brand in NATIONAL_MEGA_BROKERS:
        if brand in name_upper:
            return True
    return False


def scrape_texas_surplus_lines(
    limit: int = 5000,
    stamping_only: bool = False,
    exclude_nationals: bool = True,
    enrich_officers: bool = True,
) -> List[SurplusLinesLead]:
    """
    Pulls active surplus lines entity licensees from data.texas.gov Socrata CSV endpoint.
    """
    print(f"[*] Fetching active surplus lines agencies from data.texas.gov (3yqc-fcdt)...")
    params = urllib.parse.urlencode({
        "$where": "license_type='Surplus Lines Agency'",
        "$limit": str(limit),
    })
    base_agencies_url = f"https://data.texas.gov/resource/3yqc-fcdt.csv?{params}"
    agency_rows = fetch_socrata_csv(base_agencies_url)
    print(f"[+] Retrieved {len(agency_rows)} surplus lines agency records from Socrata.")

    officer_map: Dict[str, str] = {}
    if enrich_officers:
        print(f"[*] Fetching active officers and directors (ghh2-6wm5)...")
        officer_params = urllib.parse.urlencode({"$limit": "10000"})
        officers_url = f"https://data.texas.gov/resource/ghh2-6wm5.csv?{officer_params}"
        try:
            officer_rows = fetch_socrata_csv(officers_url)
            for row in officer_rows:
                lic = row.get("agency_license_number", "").strip()
                name = row.get("officer_director_name", "").strip()
                if lic and name and lic not in officer_map:
                    officer_map[lic] = name
            print(f"[+] Loaded {len(officer_map)} unique agency principal officers.")
        except Exception as e:
            print(f"[!] Warning: Failed to fetch officers table ({e}); continuing with base data.")

    leads: List[SurplusLinesLead] = []
    seen_licenses: Set[str] = set()

    for row in agency_rows:
        lic_id = row.get("agency_license_number", "").strip()
        company = row.get("org_name", "").strip()
        city = row.get("city", "").strip()
        state = row.get("state", "").strip().upper()
        zip_code = row.get("pstl_cd", "").strip()
        npn = row.get("npn", "").strip()

        if not lic_id or not company:
            continue
        if lic_id in seen_licenses:
            continue
        seen_licenses.add(lic_id)

        if exclude_nationals and is_national_brand(company):
            continue

        is_stamping = state in STAMPING_STATES
        if stamping_only and not is_stamping:
            continue

        officer = officer_map.get(lic_id, "")

        leads.append(
            SurplusLinesLead(
                company=company,
                city=city,
                state=state,
                license_id=lic_id,
                zip_code=zip_code,
                npn=npn,
                officer_name=officer,
                stamping_state=is_stamping,
            )
        )

    print(f"[+] Successfully harvested and deduped {len(leads)} surplus lines broker leads.")
    return leads


def export_leads_csv(leads: List[SurplusLinesLead], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company",
        "city",
        "state",
        "license_id",
        "zip_code",
        "npn",
        "officer_name",
        "stamping_state",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_dict())
    print(f"[✓] Exported {len(leads)} leads to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Texas Socrata Surplus Lines Licensee Scraper")
    parser.add_argument("--output", default="leads.csv", help="Output CSV path (default: leads.csv)")
    parser.add_argument("--limit", type=int, default=5000, help="Socrata row limit (default: 5000)")
    parser.add_argument("--stamping-only", action="store_true", help="Filter to the 15 stamping states")
    parser.add_argument("--include-nationals", action="store_true", help="Do not exclude national mega-broker brands")
    parser.add_argument("--no-enrich", action="store_true", help="Skip executive officer enrichment")

    args = parser.parse_args()
    out_file = Path(args.output).resolve()

    leads = scrape_texas_surplus_lines(
        limit=args.limit,
        stamping_only=args.stamping_only,
        exclude_nationals=not args.include_nationals,
        enrich_officers=not args.no_enrich,
    )
    export_leads_csv(leads, out_file)


if __name__ == "__main__":
    main()
