"""Validate the configuration files for the 2025 P&C profitability project."""

from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"

COMPANIES_FILE = CONFIG_DIR / "companies_2025.csv"
METRICS_FILE = CONFIG_DIR / "metrics_2025.csv"
OUTPUT_FIELDS_FILE = CONFIG_DIR / "output_fields_2025.csv"


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read one UTF-8 CSV file and return its rows."""

    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


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


def validate_configuration() -> dict[str, object]:
    """Validate all three project configuration files."""

    companies = read_csv_rows(COMPANIES_FILE)
    metrics = read_csv_rows(METRICS_FILE)
    output_fields = read_csv_rows(OUTPUT_FIELDS_FILE)

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

    if company_ids != EXPECTED_COMPANY_IDS:
        missing = EXPECTED_COMPANY_IDS - company_ids
        unexpected = company_ids - EXPECTED_COMPANY_IDS
        raise ValueError(
            f"Company configuration mismatch. "
            f"Missing: {sorted(missing)}; unexpected: {sorted(unexpected)}"
        )

    if metric_ids != EXPECTED_METRIC_IDS:
        missing = EXPECTED_METRIC_IDS - metric_ids
        unexpected = metric_ids - EXPECTED_METRIC_IDS
        raise ValueError(
            f"Metric configuration mismatch. "
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

    currencies = sorted(
        {
            row.get("reporting_currency", "").strip()
            for row in companies
            if row.get("reporting_currency", "").strip()
        }
    )

    return {
        "companies": len(companies),
        "metrics": len(metrics),
        "output_fields": len(output_fields),
        "currencies": currencies,
        "source_documents_pending": sum(
            row.get("source_status", "").strip() == "pending"
            for row in companies
        ),
    }


if __name__ == "__main__":
    result = validate_configuration()

    print("Configuration validation passed.")
    print(f"Companies: {result['companies']}")
    print(f"Metrics: {result['metrics']}")
    print(f"Output fields: {result['output_fields']}")
    print(f"Currencies: {', '.join(result['currencies'])}")
    print(
        "Source documents pending: "
        f"{result['source_documents_pending']}"
    )
