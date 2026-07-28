"""Import Taiwan non-life insurers' official underwriting ratios.

The Financial Supervisory Commission report ``RPT-06161601.csv`` contains
metadata rows before the real CSV header.  This module locates that header,
preserves the reporting year and quarter, and converts the three official
underwriting ratios into the metric IDs used by the global comparison project.

The importer remains company-independent: insurer names, years, quarters, and
reported values all come from the uploaded report or configuration files.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import BinaryIO, TextIO

import pandas as pd


REPORT_CODE = "RPT-06161601"
REPORT_NAME = "表06161601-產險財務業務指標"
REPORT_SOURCE_URL = "https://ins-info.ib.gov.tw/customer/RPT-06161601.aspx"

REQUIRED_COLUMNS = {
    "年度",
    "季度",
    "公司名稱",
    "自留綜合率",
    "自留費用率",
    "自留滿期損失率",
}

# Metric IDs must match config/metrics_2025.csv and
# config/output_fields_2025.csv.
METRIC_COLUMNS = {
    "自留綜合率": {
        "metric_id": "reported_combined_ratio",
        "metric_name": "Reported Combined Ratio",
        "ratio_denominator": "company_defined",
    },
    "自留費用率": {
        "metric_id": "expense_ratio",
        "metric_name": "Expense Ratio",
        "ratio_denominator": "company_defined",
    },
    "自留滿期損失率": {
        "metric_id": "loss_ratio",
        "metric_name": "Loss Ratio",
        "ratio_denominator": "net_premiums_earned",
    },
}

IMPORT_OUTPUT_COLUMNS = [
    "roc_year",
    "calendar_year",
    "quarter",
    "company_name",
    "metric_id",
    "metric_name",
    "value",
    "unit",
    "value_status",
    "source_type",
    "source_name",
    "period_basis",
    "validation_status",
]

COMPARISON_OUTPUT_COLUMNS = [
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
]

MAPPING_REQUIRED_COLUMNS = {
    "source_company_name",
    "company_id",
}

COMPANY_REQUIRED_COLUMNS = {
    "company_id",
    "entity_type",
    "reporting_scope",
    "reporting_currency",
    "fiscal_year",
    "accounting_basis",
}


class TaiwanMetricsImportError(ValueError):
    """Raised when an uploaded report or related configuration is invalid."""


def _read_bytes(source: str | Path | bytes | BinaryIO | TextIO) -> bytes:
    """Return bytes from a path, byte string, or file-like object."""

    if isinstance(source, bytes):
        return source

    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()

    if hasattr(source, "getvalue"):
        value = source.getvalue()
    elif hasattr(source, "read"):
        value = source.read()
    else:
        raise TypeError("source 必須是檔案路徑、bytes 或可讀取的檔案物件")

    if isinstance(value, str):
        return value.encode("utf-8")

    return bytes(value)


def _decode_report(raw: bytes) -> str:
    """Decode UTF-8 or common Traditional Chinese CSV encodings."""

    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise TaiwanMetricsImportError(
        "無法辨識 CSV 編碼；請從公開資訊網站重新下載 CSV 後再上傳。"
    )


def _read_config_csv(
    source: str | Path | bytes | BinaryIO | TextIO,
) -> pd.DataFrame:
    """Read a small UTF-8/Big5 configuration CSV as strings."""

    text = _decode_report(_read_bytes(source))
    frame = pd.read_csv(io.StringIO(text), dtype="string").fillna("")
    frame.columns = frame.columns.str.strip()
    return frame


def _find_header_row(rows: list[list[str]]) -> int:
    """Locate the actual report header after the metadata rows."""

    for index, row in enumerate(rows):
        normalized = {cell.strip() for cell in row}
        if REQUIRED_COLUMNS.issubset(normalized):
            return index

    missing = "、".join(sorted(REQUIRED_COLUMNS))
    raise TaiwanMetricsImportError(
        f"找不到財務業務指標欄位；檔案必須包含：{missing}。"
    )


def _to_number(series: pd.Series, column_name: str) -> pd.Series:
    """Convert a report column to numeric percentages."""

    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .replace({"": pd.NA, "-": pd.NA, "--": pd.NA})
    )
    values = pd.to_numeric(cleaned, errors="coerce")

    invalid = cleaned.notna() & values.isna()
    if invalid.any():
        examples = "、".join(cleaned[invalid].drop_duplicates().head(3))
        raise TaiwanMetricsImportError(
            f"欄位「{column_name}」包含無法轉換的數值：{examples}"
        )

    return values


def load_taiwan_indicator_report(
    source: str | Path | bytes | BinaryIO | TextIO,
) -> pd.DataFrame:
    """Read an RPT-06161601 CSV and return one row per insurer.

    Ratio values remain percentage points.  For example, ``88.87`` represents
    ``88.87%`` rather than ``0.8887``.
    """

    text = _decode_report(_read_bytes(source))
    rows = list(csv.reader(io.StringIO(text)))
    header_index = _find_header_row(rows)

    header = [cell.strip() for cell in rows[header_index]]
    data_rows = [
        row
        for row in rows[header_index + 1 :]
        if row and any(cell.strip() for cell in row)
    ]

    if not data_rows:
        raise TaiwanMetricsImportError("報表只有欄名，沒有任何公司資料。")

    width = len(header)
    malformed = [
        index
        for index, row in enumerate(data_rows, start=header_index + 2)
        if len(row) != width
    ]
    if malformed:
        shown = "、".join(map(str, malformed[:5]))
        raise TaiwanMetricsImportError(f"CSV 第 {shown} 列的欄位數量不正確。")

    report = pd.DataFrame(data_rows, columns=header)
    report.columns = report.columns.str.strip()

    for column in ("年度", "季度", *METRIC_COLUMNS):
        report[column] = _to_number(report[column], column)

    if report[["年度", "季度", "公司名稱"]].isna().any().any():
        raise TaiwanMetricsImportError("年度、季度或公司名稱不可為空白。")

    report["年度"] = report["年度"].astype("int64")
    report["季度"] = report["季度"].astype("int64")
    report["公司名稱"] = report["公司名稱"].astype("string").str.strip()

    invalid_quarters = ~report["季度"].between(1, 4)
    if invalid_quarters.any():
        quarters = sorted(report.loc[invalid_quarters, "季度"].unique())
        raise TaiwanMetricsImportError(f"季度必須介於 1 到 4；目前讀到：{quarters}")

    duplicates = report.duplicated(
        subset=["年度", "季度", "公司名稱"],
        keep=False,
    )
    if duplicates.any():
        companies = "、".join(
            report.loc[duplicates, "公司名稱"].drop_duplicates().head(5)
        )
        raise TaiwanMetricsImportError(f"同一期間出現重複公司：{companies}")

    return report.reset_index(drop=True)


def to_standard_metrics(report: pd.DataFrame) -> pd.DataFrame:
    """Convert the official wide report to the app's long-form import table."""

    missing = REQUIRED_COLUMNS.difference(report.columns)
    if missing:
        raise TaiwanMetricsImportError(
            f"資料缺少必要欄位：{'、'.join(sorted(missing))}"
        )

    validation_delta = (
        report["自留費用率"]
        + report["自留滿期損失率"]
        - report["自留綜合率"]
    ).abs()
    validation = validation_delta.le(0.02).map(
        {True: "passed", False: "ratio_mismatch"}
    )
    period_basis = report["季度"].eq(4).map(
        {True: "calendar_year", False: "calendar_year_to_date"}
    )

    frames: list[pd.DataFrame] = []
    for source_column, definition in METRIC_COLUMNS.items():
        frame = pd.DataFrame(
            {
                "roc_year": report["年度"],
                "calendar_year": report["年度"] + 1911,
                "quarter": report["季度"],
                "company_name": report["公司名稱"],
                "metric_id": definition["metric_id"],
                "metric_name": definition["metric_name"],
                "value": report[source_column],
                "unit": "percent",
                "value_status": "reported",
                "source_type": "official_public_disclosure_upload",
                "source_name": REPORT_NAME,
                "period_basis": period_basis,
                "validation_status": validation,
            }
        )
        frames.append(frame)

    metrics = pd.concat(frames, ignore_index=True)
    metrics = metrics[IMPORT_OUTPUT_COLUMNS]
    return metrics.sort_values(
        ["calendar_year", "quarter", "company_name", "metric_id"],
        kind="stable",
    ).reset_index(drop=True)


def import_taiwan_reported_metrics(
    source: str | Path | bytes | BinaryIO | TextIO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return both the original wide report and long-form imported metrics."""

    report = load_taiwan_indicator_report(source)
    metrics = to_standard_metrics(report)
    return report, metrics


def add_company_ids(
    metrics: pd.DataFrame,
    mapping_source: str | Path | bytes | BinaryIO | TextIO,
) -> pd.DataFrame:
    """Attach project company IDs using an external company-name mapping.

    Insurers not selected for the six-company comparison remain in the imported
    report and receive an empty ``company_id``.
    """

    required_metric_columns = {"company_name", "metric_id"}
    missing_metric_columns = required_metric_columns.difference(metrics.columns)
    if missing_metric_columns:
        raise TaiwanMetricsImportError(
            "指標資料缺少必要欄位："
            + "、".join(sorted(missing_metric_columns))
        )

    mapping = _read_config_csv(mapping_source)
    missing = MAPPING_REQUIRED_COLUMNS.difference(mapping.columns)
    if missing:
        raise TaiwanMetricsImportError(
            f"公司名稱對照檔缺少必要欄位：{'、'.join(sorted(missing))}"
        )

    mapping = mapping[["source_company_name", "company_id"]].copy()
    mapping["source_company_name"] = (
        mapping["source_company_name"].astype("string").str.strip()
    )
    mapping["company_id"] = mapping["company_id"].astype("string").str.strip()

    empty_rows = mapping[
        mapping["source_company_name"].eq("") | mapping["company_id"].eq("")
    ]
    if not empty_rows.empty:
        raise TaiwanMetricsImportError(
            "公司名稱對照檔的 source_company_name 與 company_id 不可空白。"
        )

    duplicate_names = mapping["source_company_name"].duplicated(keep=False)
    if duplicate_names.any():
        names = "、".join(
            mapping.loc[
                duplicate_names,
                "source_company_name",
            ].drop_duplicates()
        )
        raise TaiwanMetricsImportError(f"公司名稱對照重複：{names}")

    duplicate_ids = mapping["company_id"].duplicated(keep=False)
    if duplicate_ids.any():
        ids = "、".join(
            mapping.loc[duplicate_ids, "company_id"].drop_duplicates()
        )
        raise TaiwanMetricsImportError(f"company_id 對照重複：{ids}")

    mapped = metrics.merge(
        mapping,
        left_on="company_name",
        right_on="source_company_name",
        how="left",
        validate="many_to_one",
    )
    mapped = mapped.drop(columns="source_company_name")
    mapped["company_id"] = mapped["company_id"].fillna("").astype("string")

    ordered_columns = [
        "company_id",
        *[column for column in mapped.columns if column != "company_id"],
    ]
    return mapped[ordered_columns]


def _validate_company_config(companies: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the company metadata needed for output records."""

    missing = COMPANY_REQUIRED_COLUMNS.difference(companies.columns)
    if missing:
        raise TaiwanMetricsImportError(
            f"公司設定檔缺少必要欄位：{'、'.join(sorted(missing))}"
        )

    selected = companies[
        [
            "company_id",
            "entity_type",
            "reporting_scope",
            "reporting_currency",
            "fiscal_year",
            "accounting_basis",
        ]
    ].copy()

    for column in selected.columns:
        selected[column] = selected[column].astype("string").str.strip()

    required_text_columns = COMPANY_REQUIRED_COLUMNS - {"fiscal_year"}
    blank_columns = [
        column
        for column in sorted(required_text_columns)
        if selected[column].eq("").any()
    ]
    if blank_columns:
        raise TaiwanMetricsImportError(
            "公司設定檔不可留白的欄位："
            + "、".join(blank_columns)
        )

    selected["fiscal_year"] = pd.to_numeric(
        selected["fiscal_year"],
        errors="coerce",
    )
    if selected["fiscal_year"].isna().any():
        raise TaiwanMetricsImportError("公司設定檔的 fiscal_year 必須是整數。")
    selected["fiscal_year"] = selected["fiscal_year"].astype("int64")

    duplicate_ids = selected["company_id"].duplicated(keep=False)
    if duplicate_ids.any():
        ids = "、".join(
            selected.loc[duplicate_ids, "company_id"].drop_duplicates()
        )
        raise TaiwanMetricsImportError(f"公司設定檔 company_id 重複：{ids}")

    return selected


def _period_dates(
    years: pd.Series,
    quarters: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Return ISO period start and cumulative quarter-end dates."""

    starts = pd.to_datetime(
        years.astype("int64").astype("string") + "-01-01"
    )
    quarter_end_months = quarters.astype("int64") * 3
    ends = pd.to_datetime(
        [
            f"{int(year):04d}-{int(month):02d}-01"
            for year, month in zip(years, quarter_end_months)
        ]
    ) + pd.offsets.MonthEnd(0)
    return starts.dt.strftime("%Y-%m-%d"), ends.to_series(
        index=years.index
    ).dt.strftime("%Y-%m-%d")


def to_comparison_records(
    metrics: pd.DataFrame,
    companies_source: str | Path | bytes | BinaryIO | TextIO,
) -> pd.DataFrame:
    """Convert mapped Taiwan ratios to the project's 27-column output schema.

    Only insurers with a non-empty ``company_id`` are included.  Unmapped
    insurers remain available in the import table but are intentionally omitted
    from the six-company comparison output.
    """

    required_columns = {
        "company_id",
        "company_name",
        "roc_year",
        "calendar_year",
        "quarter",
        "metric_id",
        "value",
        "unit",
        "value_status",
        "source_name",
        "period_basis",
        "validation_status",
    }
    missing = required_columns.difference(metrics.columns)
    if missing:
        raise TaiwanMetricsImportError(
            "轉換全球比較格式前缺少欄位："
            + "、".join(sorted(missing))
        )

    comparable = metrics.loc[
        metrics["company_id"].astype("string").str.strip().ne("")
    ].copy()
    if comparable.empty:
        raise TaiwanMetricsImportError(
            "沒有任何公司連接至全球比較設定；請檢查公司名稱對照檔。"
        )

    allowed_metric_ids = {
        definition["metric_id"] for definition in METRIC_COLUMNS.values()
    }
    unexpected_metric_ids = (
        set(comparable["metric_id"].dropna().astype(str))
        - allowed_metric_ids
    )
    if unexpected_metric_ids:
        raise TaiwanMetricsImportError(
            "台灣官方指標包含未支援的 metric_id："
            + "、".join(sorted(unexpected_metric_ids))
        )

    companies = _validate_company_config(
        _read_config_csv(companies_source)
    )
    comparable = comparable.merge(
        companies,
        on="company_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    missing_company_ids = sorted(
        comparable.loc[
            comparable["_merge"].ne("both"),
            "company_id",
        ].drop_duplicates()
    )
    if missing_company_ids:
        raise TaiwanMetricsImportError(
            "companies_2025.csv 找不到 company_id："
            + "、".join(missing_company_ids)
        )
    comparable = comparable.drop(columns="_merge")

    year_mismatch = comparable["calendar_year"].astype("int64").ne(
        comparable["fiscal_year"]
    )
    if year_mismatch.any():
        ids = "、".join(
            comparable.loc[year_mismatch, "company_id"].drop_duplicates()
        )
        raise TaiwanMetricsImportError(
            f"上傳年度與公司設定的 fiscal_year 不一致：{ids}"
        )

    period_start, period_end = _period_dates(
        comparable["calendar_year"],
        comparable["quarter"],
    )

    source_column_by_metric = {
        definition["metric_id"]: source_column
        for source_column, definition in METRIC_COLUMNS.items()
    }
    denominator_by_metric = {
        definition["metric_id"]: definition["ratio_denominator"]
        for definition in METRIC_COLUMNS.values()
    }

    official_metric_name = comparable["metric_id"].map(
        source_column_by_metric
    )
    evidence_text = (
        comparable["company_name"].astype("string")
        + "｜民國"
        + comparable["roc_year"].astype("int64").astype("string")
        + "年第"
        + comparable["quarter"].astype("int64").astype("string")
        + "季｜"
        + official_metric_name.astype("string")
        + "："
        + comparable["value"].map(lambda value: f"{value:g}")
        + "%"
    )

    output = pd.DataFrame(
        {
            "record_id": (
                "taiwan_"
                + comparable["company_id"].astype("string")
                + "_"
                + comparable["calendar_year"].astype("int64").astype("string")
                + "_q"
                + comparable["quarter"].astype("int64").astype("string")
                + "_"
                + comparable["metric_id"].astype("string")
            ),
            "company_id": comparable["company_id"],
            "reporting_scope": comparable["reporting_scope"],
            "entity_type": comparable["entity_type"],
            "fiscal_year": comparable["calendar_year"].astype("int64"),
            "period_start": period_start,
            "period_end": period_end,
            "metric_id": comparable["metric_id"],
            "metric_value": comparable["value"],
            "metric_unit": "percent",
            "currency": "not_applicable",
            "monetary_scale": "not_applicable",
            "value_base_units": pd.NA,
            "year_basis": comparable["period_basis"],
            "adjustment_basis": "reported",
            "ratio_denominator": comparable["metric_id"].map(
                denominator_by_metric
            ),
            "value_origin": comparable["value_status"],
            "accounting_basis": comparable["accounting_basis"],
            "source_document": comparable["source_name"],
            "source_url": REPORT_SOURCE_URL,
            "source_page": REPORT_CODE,
            "chunk_id": "",
            "evidence_text": evidence_text,
            "definition_note": (
                "官方揭露之"
                + official_metric_name.astype("string")
                + "；保留原始揭露值，未由程式重新計算。"
            ),
            "confidence_score": 1.0,
            "validation_status": comparable["validation_status"].map(
                {"passed": "verified", "ratio_mismatch": "warning"}
            ),
            "warning_message": comparable["validation_status"].map(
                {
                    "passed": "",
                    "ratio_mismatch": (
                        "自留費用率與自留滿期損失率之和，"
                        "和自留綜合率差異超過0.02個百分點。"
                    ),
                }
            ),
        }
    )

    if output["validation_status"].isna().any():
        statuses = sorted(
            comparable.loc[
                output["validation_status"].isna(),
                "validation_status",
            ].drop_duplicates()
        )
        raise TaiwanMetricsImportError(
            "無法轉換 validation_status："
            + "、".join(map(str, statuses))
        )

    output = output[COMPARISON_OUTPUT_COLUMNS]
    return output.sort_values(
        ["fiscal_year", "company_id", "metric_id"],
        kind="stable",
    ).reset_index(drop=True)


def company_metric_summary(
    metrics: pd.DataFrame,
    company_name: str,
    *,
    calendar_year: int | None = None,
    quarter: int | None = None,
) -> pd.DataFrame:
    """Select one insurer and pivot its reported ratios for display."""

    selected = metrics.loc[metrics["company_name"].eq(company_name)].copy()

    if calendar_year is not None:
        selected = selected.loc[selected["calendar_year"].eq(calendar_year)]
    if quarter is not None:
        selected = selected.loc[selected["quarter"].eq(quarter)]

    if selected.empty:
        raise TaiwanMetricsImportError(
            f"上傳報表中找不到公司「{company_name}」或指定期間。"
        )

    index_columns = [
        "roc_year",
        "calendar_year",
        "quarter",
        "company_name",
        "value_status",
        "source_name",
        "validation_status",
    ]
    summary = selected.pivot(
        index=index_columns,
        columns="metric_id",
        values="value",
    ).reset_index()
    summary.columns.name = None

    # Temporary compatibility aliases keep the current Streamlit section
    # working until streamlit_taiwan_import_section.py is updated.
    if "loss_ratio" in summary and "reported_loss_ratio" not in summary:
        summary["reported_loss_ratio"] = summary["loss_ratio"]
    if "expense_ratio" in summary and "reported_expense_ratio" not in summary:
        summary["reported_expense_ratio"] = summary["expense_ratio"]

    return summary
