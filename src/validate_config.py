"""Validate configuration files for the 2025 P&C profitability project."""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"

COMPANIES_FILE = CONFIG_DIR / "companies_2025.csv"
METRICS_FILE = CONFIG_DIR / "metrics_2025.csv"
OUTPUT_FIELDS_FILE = CONFIG_DIR / "output_fields_2025.csv"
SOURCES_FILE = CONFIG_DIR / "sources_2025.csv"


EXPECTED_COMPANY_IDS = {
    "cathay_century",
    "fubon_insurance",
    "lloyds_market",
    "chubb_p_and_c",
    "liberty_mutual",
    "progressive",
}

EXPECTED_METRIC_IDS = {
    "reported_combined_ratio",
    "underlying_adjusted_combined_ratio",
    "loss_ratio",
    "expense_ratio",
    "underwriting_result",
    "earned_premium_or_insurance_revenue",
}

REQUIRED_OUTPUT_FIELDS = {
    "record_id",
    "company_id",
    "reporting_scope",
    "entity_type",
    "fiscal_year",
    "period_start",
    "period_end",
    "metric_id",
    "metric_value",
    "metric_unit",
    "currency",
    "monetary_scale",
    "value_base_units",
    "year_basis",
    "adjustment_basis",
    "ratio_denominator",
    "value_origin",
    "accounting_basis",
    "source_document",
    "source_url",
    "source_page",
    "chunk_id",
    "evidence_text",
    "definition_note",
    "confidence_score",
    "validation_status",
    "warning_message",
}

REQUIRED_SOURCE_COLUMNS = {
    "source_id",
    "company_id",
    "source_title",
    "source_type",
    "source_url",
    "reporting_period",
    "reporting_scope",
    "currency",
    "monetary_scale",
    "official_source",
    "source_status",
    "notes",
}

ALLOWED_SOURCE_TYPES = {"html", "pdf", "csv", "xlsx"}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read one UTF-8 CSV file and return its rows."""

    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: missing CSV header")
        return list(reader)


def require_columns(
    rows: list[dict[str, str]],
    required_columns: set[str],
    file_name: str,
) -> None:
    """Reject a CSV when required columns are absent."""

    if not rows:
        raise ValueError(f"{file_name}: no data rows found")

    actual_columns = set(rows[0])
    missing_columns = required_columns - actual_columns
    if missing_columns:
        raise ValueError(
            f"{file_name}: missing columns {sorted(missing_columns)}"
        )


def validate_unique_values(
    rows: list[dict[str, str]],
    column: str,
    file_name: str,
) -> set[str]:
    """Return unique non-empty values and reject duplicates."""

    values = [row.get(column, "").strip() for row in rows]

    if any(not value for value in values):
        raise ValueError(f"{file_name}: blank value found in {column}")

    if len(values) != len(set(values)):
        raise ValueError(f"{file_name}: duplicate value found in {column}")

    return set(values)


def is_http_url(value: str) -> bool:
    """Return whether a value is an absolute HTTP or HTTPS URL."""

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_configuration() -> dict[str, object]:
    """Validate all project configuration files."""

    companies = read_csv_rows(COMPANIES_FILE)
    metrics = read_csv_rows(METRICS_FILE)
    output_fields = read_csv_rows(OUTPUT_FIELDS_FILE)
    sources = read_csv_rows(SOURCES_FILE)

    require_columns(sources, REQUIRED_SOURCE_COLUMNS, SOURCES_FILE.name)

    company_ids = validate_unique_values(
        companies,
        "company_id",
        COMPANIES_FILE.name,
    )
    metric_ids = validate_unique_values(
        metrics,
        "metric_id",
        METRICS_FILE.name,
    )
    output_field_names = validate_unique_values(
        output_fields,
        "field_name",
        OUTPUT_FIELDS_FILE.name,
    )
    validate_unique_values(
        sources,
        "source_id",
        SOURCES_FILE.name,
    )

    if company_ids != EXPECTED_COMPANY_IDS:
        missing = EXPECTED_COMPANY_IDS - company_ids
        unexpected = company_ids - EXPECTED_COMPANY_IDS
        raise ValueError(
            "Company configuration mismatch. "
            f"Missing: {sorted(missing)}; unexpected: {sorted(unexpected)}"
        )

    if metric_ids != EXPECTED_METRIC_IDS:
        missing = EXPECTED_METRIC_IDS - metric_ids
        unexpected = metric_ids - EXPECTED_METRIC_IDS
        raise ValueError(
            "Metric configuration mismatch. "
            f"Missing: {sorted(missing)}; unexpected: {sorted(unexpected)}"
        )

    missing_output_fields = REQUIRED_OUTPUT_FIELDS - output_field_names
    if missing_output_fields:
        raise ValueError(
            f"Missing output fields: {sorted(missing_output_fields)}"
        )

    invalid_years = [
        row["company_id"]
        for row in companies
        if row.get("fiscal_year", "").strip() != "2025"
    ]
    if invalid_years:
        raise ValueError(
            f"Companies with an invalid fiscal year: {invalid_years}"
        )

    source_company_ids = {
        row.get("company_id", "").strip()
        for row in sources
    }
    unknown_source_companies = source_company_ids - company_ids
    if unknown_source_companies:
        raise ValueError(
            "Sources reference unknown company IDs: "
            f"{sorted(unknown_source_companies)}"
        )

    invalid_source_types = sorted(
        {
            row.get("source_type", "").strip().lower()
            for row in sources
            if row.get("source_type", "").strip().lower()
            not in ALLOWED_SOURCE_TYPES
        }
    )
    if invalid_source_types:
        raise ValueError(
            f"Unsupported source types: {invalid_source_types}"
        )

    invalid_urls = [
        row["source_id"]
        for row in sources
        if not is_http_url(row.get("source_url", "").strip())
    ]
    if invalid_urls:
        raise ValueError(
            f"Sources with invalid URLs: {invalid_urls}"
        )

    companies_without_sources = sorted(company_ids - source_company_ids)
    currencies = sorted(
        {
            row.get("reporting_currency", "").strip()
            for row in companies
            if row.get("reporting_currency", "").strip()
        }
    )
    sources_needing_review = sum(
        "review" in row.get("source_status", "").strip().lower()
        for row in sources
    )

    return {
        "companies": len(companies),
        "metrics": len(metrics),
        "output_fields": len(output_fields),
        "currencies": currencies,
        "source_records": len(sources),
        "companies_with_sources": len(source_company_ids),
        "companies_without_sources": len(companies_without_sources),
        "company_ids_without_sources": companies_without_sources,
        "sources_needing_review": sources_needing_review,
    }


if __name__ == "__main__":
    result = validate_configuration()

    print("Configuration validation passed.")
    print(f"Companies: {result['companies']}")
    print(f"Metrics: {result['metrics']}")
    print(f"Output fields: {result['output_fields']}")
    print(f"Currencies: {', '.join(result['currencies'])}")
    print(f"Source records: {result['source_records']}")
    print(f"Companies with sources: {result['companies_with_sources']}")
    print(f"Companies without sources: {result['companies_without_sources']}")
    print(f"Sources needing review: {result['sources_needing_review']}")
