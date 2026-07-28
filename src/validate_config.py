"""Validate configuration files for the 2025 P&C profitability project.

The validator checks each configuration file independently and verifies the
relationships between companies, metrics, output fields, source records,
Taiwan company-name mappings, and multilingual metric rules.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"

COMPANIES_FILE = CONFIG_DIR / "companies_2025.csv"
METRICS_FILE = CONFIG_DIR / "metrics_2025.csv"
OUTPUT_FIELDS_FILE = CONFIG_DIR / "output_fields_2025.csv"
SOURCES_FILE = CONFIG_DIR / "sources_2025.csv"
TAIWAN_MAPPING_FILE = CONFIG_DIR / "taiwan_company_mapping.csv"
METRIC_RULES_FILE = CONFIG_DIR / "metric_rules_2025.json"


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

REQUIRED_COMPANY_COLUMNS = {
    "company_id",
    "display_name_zh",
    "display_name_en",
    "legal_entity_or_market",
    "entity_type",
    "reporting_scope",
    "home_market",
    "reporting_currency",
    "fiscal_year",
    "fiscal_year_end",
    "accounting_basis",
    "annual_report_url",
    "source_status",
}

REQUIRED_METRIC_COLUMNS = {
    "metric_id",
    "display_name",
    "metric_category",
    "value_type",
    "default_unit",
    "currency_required",
    "monetary_scale_required",
    "year_basis_required",
    "default_adjustment_basis",
    "comparison_role",
    "ranking_direction",
}

REQUIRED_OUTPUT_FIELD_COLUMNS = {
    "field_name",
    "data_type",
    "required",
    "allowed_values",
    "description",
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

REQUIRED_TAIWAN_MAPPING_COLUMNS = {
    "source_company_name",
    "company_id",
}

ALLOWED_SOURCE_TYPES = {"html", "pdf", "csv", "xlsx"}
ALLOWED_SOURCE_SCALES = {
    "unit",
    "thousand",
    "million",
    "billion",
    "mixed",
    "not_applicable",
}
ALLOWED_VALUE_TYPES = {"percentage", "monetary"}
ALLOWED_OUTPUT_DATA_TYPES = {"string", "integer", "date", "number"}
BOOLEAN_VALUES = {"true", "false"}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read one UTF-8 CSV file and return stripped string rows."""

    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: missing CSV header")

        normalized_headers = [
            header.strip() if header is not None else ""
            for header in reader.fieldnames
        ]
        if any(not header for header in normalized_headers):
            raise ValueError(f"{path.name}: blank CSV header found")
        if len(normalized_headers) != len(set(normalized_headers)):
            raise ValueError(f"{path.name}: duplicate CSV header found")

        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"{path.name}: row {row_number} has too many values"
                )

            normalized_row = {
                (key.strip() if key is not None else ""): (
                    value.strip() if value is not None else ""
                )
                for key, value in row.items()
            }
            if any(normalized_row.values()):
                rows.append(normalized_row)

    if not rows:
        raise ValueError(f"{path.name}: no data rows found")

    return rows


def read_json_object(path: Path) -> dict[str, Any]:
    """Read a UTF-8 JSON file and require a top-level object."""

    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path.name}: invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: top-level JSON value must be an object")

    return value


def require_columns(
    rows: list[dict[str, str]],
    required_columns: set[str],
    file_name: str,
) -> None:
    """Reject a CSV when required columns are absent."""

    actual_columns = set(rows[0])
    missing_columns = required_columns - actual_columns
    if missing_columns:
        raise ValueError(
            f"{file_name}: missing columns {sorted(missing_columns)}"
        )


def require_non_blank(
    rows: list[dict[str, str]],
    columns: set[str],
    file_name: str,
) -> None:
    """Reject blank values in columns that must contain data."""

    for row_number, row in enumerate(rows, start=2):
        missing = sorted(column for column in columns if not row.get(column, ""))
        if missing:
            raise ValueError(
                f"{file_name}: row {row_number} has blank values in {missing}"
            )


def validate_unique_values(
    rows: list[dict[str, str]],
    column: str,
    file_name: str,
) -> set[str]:
    """Return unique non-empty values and reject duplicates."""

    values = [row.get(column, "") for row in rows]

    if any(not value for value in values):
        raise ValueError(f"{file_name}: blank value found in {column}")

    duplicates = sorted(
        {value for value in values if values.count(value) > 1}
    )
    if duplicates:
        raise ValueError(
            f"{file_name}: duplicate values in {column}: {duplicates}"
        )

    return set(values)


def parse_allowed_values(
    output_fields: list[dict[str, str]],
) -> dict[str, set[str]]:
    """Return pipe-delimited allowed values keyed by output field name."""

    allowed_by_field: dict[str, set[str]] = {}
    for row in output_fields:
        raw_values = row.get("allowed_values", "")
        values = [value.strip() for value in raw_values.split("|") if value.strip()]
        if len(values) != len(set(values)):
            raise ValueError(
                f"{OUTPUT_FIELDS_FILE.name}: duplicate allowed value for "
                f"{row.get('field_name', '')}"
            )
        allowed_by_field[row["field_name"]] = set(values)

    return allowed_by_field


def is_http_url(value: str) -> bool:
    """Return whether a value is an absolute HTTP or HTTPS URL."""

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def require_exact_ids(
    actual_ids: set[str],
    expected_ids: set[str],
    label: str,
) -> None:
    """Reject missing or unexpected identifiers."""

    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        raise ValueError(
            f"{label} mismatch. Missing: {missing}; unexpected: {unexpected}"
        )


def validate_output_fields(
    output_fields: list[dict[str, str]],
    metric_ids: set[str],
) -> dict[str, set[str]]:
    """Validate the 27-field comparison output schema."""

    require_columns(
        output_fields,
        REQUIRED_OUTPUT_FIELD_COLUMNS,
        OUTPUT_FIELDS_FILE.name,
    )
    require_non_blank(
        output_fields,
        {"field_name", "data_type", "required", "description"},
        OUTPUT_FIELDS_FILE.name,
    )

    output_field_names = validate_unique_values(
        output_fields,
        "field_name",
        OUTPUT_FIELDS_FILE.name,
    )
    require_exact_ids(
        output_field_names,
        REQUIRED_OUTPUT_FIELDS,
        "Output field configuration",
    )

    invalid_data_types = sorted(
        {
            row["data_type"]
            for row in output_fields
            if row["data_type"] not in ALLOWED_OUTPUT_DATA_TYPES
        }
    )
    if invalid_data_types:
        raise ValueError(
            f"{OUTPUT_FIELDS_FILE.name}: unsupported data types "
            f"{invalid_data_types}"
        )

    invalid_required_values = sorted(
        {
            row["required"].lower()
            for row in output_fields
            if row["required"].lower() not in BOOLEAN_VALUES
        }
    )
    if invalid_required_values:
        raise ValueError(
            f"{OUTPUT_FIELDS_FILE.name}: required must be true or false; "
            f"found {invalid_required_values}"
        )

    allowed_by_field = parse_allowed_values(output_fields)

    configured_metric_ids = allowed_by_field.get("metric_id", set())
    require_exact_ids(
        configured_metric_ids,
        metric_ids,
        "output_fields_2025.csv metric_id allowed values",
    )

    year_basis_values = allowed_by_field.get("year_basis", set())
    if "calendar_year_to_date" not in year_basis_values:
        raise ValueError(
            f"{OUTPUT_FIELDS_FILE.name}: year_basis must allow "
            "calendar_year_to_date for Taiwan quarterly reports"
        )

    return allowed_by_field


def validate_companies(
    companies: list[dict[str, str]],
    allowed_by_field: dict[str, set[str]],
) -> set[str]:
    """Validate the six comparison-company records."""

    require_columns(companies, REQUIRED_COMPANY_COLUMNS, COMPANIES_FILE.name)
    require_non_blank(
        companies,
        REQUIRED_COMPANY_COLUMNS,
        COMPANIES_FILE.name,
    )

    company_ids = validate_unique_values(
        companies,
        "company_id",
        COMPANIES_FILE.name,
    )
    require_exact_ids(company_ids, EXPECTED_COMPANY_IDS, "Company configuration")

    invalid_years = [
        row["company_id"]
        for row in companies
        if row["fiscal_year"] != "2025"
    ]
    if invalid_years:
        raise ValueError(
            f"Companies with an invalid fiscal year: {invalid_years}"
        )

    invalid_year_ends = [
        row["company_id"]
        for row in companies
        if row["fiscal_year_end"] != "2025-12-31"
    ]
    if invalid_year_ends:
        raise ValueError(
            f"Companies with an invalid fiscal year end: {invalid_year_ends}"
        )

    for company_field, output_field in (
        ("entity_type", "entity_type"),
        ("reporting_currency", "currency"),
        ("accounting_basis", "accounting_basis"),
    ):
        allowed = allowed_by_field.get(output_field, set())
        invalid = sorted(
            {
                row[company_field]
                for row in companies
                if row[company_field] not in allowed
            }
        )
        if invalid:
            raise ValueError(
                f"{COMPANIES_FILE.name}: {company_field} values not allowed by "
                f"{OUTPUT_FIELDS_FILE.name}: {invalid}"
            )

    invalid_urls = [
        row["company_id"]
        for row in companies
        if not is_http_url(row["annual_report_url"])
    ]
    if invalid_urls:
        raise ValueError(
            f"Companies with invalid annual report URLs: {invalid_urls}"
        )

    return company_ids


def validate_metrics(
    metrics: list[dict[str, str]],
    allowed_by_field: dict[str, set[str]],
) -> set[str]:
    """Validate metric definitions and output-schema compatibility."""

    require_columns(metrics, REQUIRED_METRIC_COLUMNS, METRICS_FILE.name)
    require_non_blank(metrics, REQUIRED_METRIC_COLUMNS, METRICS_FILE.name)

    metric_ids = validate_unique_values(
        metrics,
        "metric_id",
        METRICS_FILE.name,
    )
    require_exact_ids(metric_ids, EXPECTED_METRIC_IDS, "Metric configuration")

    invalid_value_types = sorted(
        {
            row["value_type"]
            for row in metrics
            if row["value_type"] not in ALLOWED_VALUE_TYPES
        }
    )
    if invalid_value_types:
        raise ValueError(
            f"{METRICS_FILE.name}: unsupported value types "
            f"{invalid_value_types}"
        )

    for boolean_column in (
        "currency_required",
        "monetary_scale_required",
        "year_basis_required",
    ):
        invalid = sorted(
            {
                row[boolean_column].lower()
                for row in metrics
                if row[boolean_column].lower() not in BOOLEAN_VALUES
            }
        )
        if invalid:
            raise ValueError(
                f"{METRICS_FILE.name}: {boolean_column} must be true or false; "
                f"found {invalid}"
            )

    allowed_adjustments = allowed_by_field.get("adjustment_basis", set())
    invalid_adjustments = sorted(
        {
            row["default_adjustment_basis"]
            for row in metrics
            if row["default_adjustment_basis"] not in allowed_adjustments
        }
    )
    if invalid_adjustments:
        raise ValueError(
            f"{METRICS_FILE.name}: default_adjustment_basis values not allowed "
            f"by {OUTPUT_FIELDS_FILE.name}: {invalid_adjustments}"
        )

    for row in metrics:
        metric_id = row["metric_id"]
        value_type = row["value_type"]
        default_unit = row["default_unit"]

        if value_type == "percentage" and default_unit != "percent":
            raise ValueError(
                f"{METRICS_FILE.name}: {metric_id} must use percent as "
                "default_unit"
            )
        if value_type == "monetary" and default_unit != "reporting_currency":
            raise ValueError(
                f"{METRICS_FILE.name}: {metric_id} must use "
                "reporting_currency as default_unit"
            )

    return metric_ids


def validate_sources(
    sources: list[dict[str, str]],
    company_ids: set[str],
) -> tuple[set[str], int]:
    """Validate official source records and their company references."""

    require_columns(sources, REQUIRED_SOURCE_COLUMNS, SOURCES_FILE.name)
    require_non_blank(
        sources,
        REQUIRED_SOURCE_COLUMNS - {"notes"},
        SOURCES_FILE.name,
    )
    validate_unique_values(sources, "source_id", SOURCES_FILE.name)

    source_company_ids = {row["company_id"] for row in sources}
    unknown_source_companies = source_company_ids - company_ids
    if unknown_source_companies:
        raise ValueError(
            "Sources reference unknown company IDs: "
            f"{sorted(unknown_source_companies)}"
        )

    invalid_source_types = sorted(
        {
            row["source_type"].lower()
            for row in sources
            if row["source_type"].lower() not in ALLOWED_SOURCE_TYPES
        }
    )
    if invalid_source_types:
        raise ValueError(
            f"Unsupported source types: {invalid_source_types}"
        )

    invalid_scales = sorted(
        {
            row["monetary_scale"]
            for row in sources
            if row["monetary_scale"] not in ALLOWED_SOURCE_SCALES
        }
    )
    if invalid_scales:
        raise ValueError(
            f"{SOURCES_FILE.name}: unsupported monetary scales {invalid_scales}"
        )

    invalid_periods = [
        row["source_id"]
        for row in sources
        if row["reporting_period"] != "2025"
    ]
    if invalid_periods:
        raise ValueError(
            f"Sources with an invalid reporting period: {invalid_periods}"
        )

    invalid_official_values = [
        row["source_id"]
        for row in sources
        if row["official_source"].lower() not in BOOLEAN_VALUES
    ]
    if invalid_official_values:
        raise ValueError(
            "Sources with invalid official_source values: "
            f"{invalid_official_values}"
        )

    invalid_urls = [
        row["source_id"]
        for row in sources
        if not is_http_url(row["source_url"])
    ]
    if invalid_urls:
        raise ValueError(
            f"Sources with invalid URLs: {invalid_urls}"
        )

    sources_needing_review = sum(
        "review" in row["source_status"].lower()
        for row in sources
    )
    return source_company_ids, sources_needing_review


def validate_taiwan_mapping(
    mapping: list[dict[str, str]],
    company_ids: set[str],
) -> set[str]:
    """Validate Taiwan disclosure names and project company IDs."""

    require_columns(
        mapping,
        REQUIRED_TAIWAN_MAPPING_COLUMNS,
        TAIWAN_MAPPING_FILE.name,
    )
    require_non_blank(
        mapping,
        REQUIRED_TAIWAN_MAPPING_COLUMNS,
        TAIWAN_MAPPING_FILE.name,
    )

    validate_unique_values(
        mapping,
        "source_company_name",
        TAIWAN_MAPPING_FILE.name,
    )
    mapped_company_ids = validate_unique_values(
        mapping,
        "company_id",
        TAIWAN_MAPPING_FILE.name,
    )

    unknown_ids = mapped_company_ids - company_ids
    if unknown_ids:
        raise ValueError(
            f"{TAIWAN_MAPPING_FILE.name}: unknown company IDs "
            f"{sorted(unknown_ids)}"
        )

    return mapped_company_ids


def validate_term_list(
    rule: dict[str, Any],
    field_name: str,
    metric_id: str,
    *,
    allow_empty: bool,
) -> None:
    """Validate one list of multilingual search terms."""

    value = rule.get(field_name)
    if not isinstance(value, list):
        raise ValueError(
            f"{METRIC_RULES_FILE.name}: {metric_id}.{field_name} must be a list"
        )
    if not allow_empty and not value:
        raise ValueError(
            f"{METRIC_RULES_FILE.name}: {metric_id}.{field_name} cannot be empty"
        )
    if any(not isinstance(term, str) or not term.strip() for term in value):
        raise ValueError(
            f"{METRIC_RULES_FILE.name}: {metric_id}.{field_name} contains "
            "a blank or non-string term"
        )

    normalized = [term.strip().casefold() for term in value]
    if len(normalized) != len(set(normalized)):
        raise ValueError(
            f"{METRIC_RULES_FILE.name}: {metric_id}.{field_name} contains "
            "duplicate terms"
        )


def validate_metric_rules(
    rules_document: dict[str, Any],
    metrics: list[dict[str, str]],
    metric_ids: set[str],
) -> None:
    """Validate multilingual search rules against metric definitions."""

    version = rules_document.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{METRIC_RULES_FILE.name}: version is required")

    rules = rules_document.get("metrics")
    if not isinstance(rules, dict):
        raise ValueError(
            f"{METRIC_RULES_FILE.name}: metrics must be a JSON object"
        )

    rule_ids = set(rules)
    require_exact_ids(
        rule_ids,
        metric_ids,
        "metric_rules_2025.json metric IDs",
    )

    metric_types = {
        row["metric_id"]: row["value_type"]
        for row in metrics
    }

    for metric_id in sorted(metric_ids):
        rule = rules[metric_id]
        if not isinstance(rule, dict):
            raise ValueError(
                f"{METRIC_RULES_FILE.name}: rule for {metric_id} must be "
                "an object"
            )

        rule_value_type = rule.get("value_type")
        if rule_value_type != metric_types[metric_id]:
            raise ValueError(
                f"{METRIC_RULES_FILE.name}: {metric_id}.value_type "
                f"({rule_value_type!r}) does not match {METRICS_FILE.name} "
                f"({metric_types[metric_id]!r})"
            )

        validate_term_list(
            rule,
            "positive_terms",
            metric_id,
            allow_empty=False,
        )
        validate_term_list(
            rule,
            "preferred_context_terms",
            metric_id,
            allow_empty=False,
        )
        validate_term_list(
            rule,
            "exclude_terms",
            metric_id,
            allow_empty=True,
        )

        if rule_value_type == "percentage":
            minimum = rule.get("percentage_min")
            maximum = rule.get("percentage_max")
            if (
                isinstance(minimum, bool)
                or isinstance(maximum, bool)
                or not isinstance(minimum, (int, float))
                or not isinstance(maximum, (int, float))
                or minimum >= maximum
            ):
                raise ValueError(
                    f"{METRIC_RULES_FILE.name}: {metric_id} must have numeric "
                    "percentage_min < percentage_max"
                )
        else:
            if not isinstance(rule.get("allow_negative"), bool):
                raise ValueError(
                    f"{METRIC_RULES_FILE.name}: {metric_id}.allow_negative "
                    "must be true or false"
                )


def validate_configuration() -> dict[str, object]:
    """Validate every project configuration file and cross-file reference."""

    companies = read_csv_rows(COMPANIES_FILE)
    metrics = read_csv_rows(METRICS_FILE)
    output_fields = read_csv_rows(OUTPUT_FIELDS_FILE)
    sources = read_csv_rows(SOURCES_FILE)
    taiwan_mapping = read_csv_rows(TAIWAN_MAPPING_FILE)
    metric_rules = read_json_object(METRIC_RULES_FILE)

    require_columns(metrics, REQUIRED_METRIC_COLUMNS, METRICS_FILE.name)
    metric_ids = validate_unique_values(
        metrics,
        "metric_id",
        METRICS_FILE.name,
    )
    require_exact_ids(metric_ids, EXPECTED_METRIC_IDS, "Metric configuration")

    allowed_by_field = validate_output_fields(output_fields, metric_ids)
    company_ids = validate_companies(companies, allowed_by_field)
    validate_metrics(metrics, allowed_by_field)
    source_company_ids, sources_needing_review = validate_sources(
        sources,
        company_ids,
    )
    mapped_company_ids = validate_taiwan_mapping(
        taiwan_mapping,
        company_ids,
    )
    validate_metric_rules(metric_rules, metrics, metric_ids)

    companies_without_sources = sorted(company_ids - source_company_ids)
    currencies = sorted({row["reporting_currency"] for row in companies})

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
        "taiwan_mapping_records": len(taiwan_mapping),
        "taiwan_companies_mapped": len(mapped_company_ids),
        "metric_rule_records": len(metric_rules["metrics"]),
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
    print(f"Taiwan mappings: {result['taiwan_mapping_records']}")
    print(f"Metric rules: {result['metric_rule_records']}")
