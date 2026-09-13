from __future__ import annotations

from research.financial_jepa.contracts import TENOR_FIELDS, JsonValue
from research.financial_jepa.treasury import URL_TEMPLATE, CacheMetadata


def cache_metadata_record(metadata: CacheMetadata) -> dict[str, JsonValue]:
    return {
        "year": metadata.year,
        "url": metadata.url,
        "retrieved_at_utc": metadata.retrieved_at_utc,
        "status_code": metadata.status_code,
        "content_type": metadata.content_type,
        "etag": metadata.etag,
        "last_modified": metadata.last_modified,
        "sha256": metadata.sha256,
        "byte_count": metadata.byte_count,
    }


def rights_metadata() -> dict[str, JsonValue]:
    selected_fields: list[JsonValue] = list(TENOR_FIELDS)
    record: dict[str, JsonValue] = {
        "publisher": "U.S. Department of the Treasury",
        "dataset_title": "Daily Treasury Par Yield Curve Rates",
        "landing_url": (
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "TextView?type=daily_treasury_yield_curve"
        ),
        "api_url_template": URL_TEMPLATE,
        "license_expression": "NOASSERTION",
        "copyright_assessment": (
            "Qualified U.S. government-work assessment under 17 U.S.C. 105; no worldwide "
            "public-domain or rights assertion is made."
        ),
        "transformation": (
            "Treasury-published derived par yields only; no underlying dealer quotes."
        ),
        "selected_fields": selected_fields,
        "copyright_basis_url": (
            "https://uscode.house.gov/view.xhtml?req=title%3A17%20section%3A105"
        ),
        "methodology_url": (
            "https://home.treasury.gov/policy-issues/financing-the-government/"
            "interest-rate-statistics/treasury-yield-curve-methodology"
        ),
        "endorsement": "No U.S. government or Treasury endorsement is implied.",
    }
    return record
