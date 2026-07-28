"""Import reported metrics from Taiwan non-life insurance public disclosures.

The Financial Supervisory Commission export ``RPT-06161601.csv`` contains
report metadata before the real header row.  This module locates the header
dynamically, preserves the report's year and quarter, and converts the three
official underwriting ratios into a stable schema used by the comparison app.

No insurer name, year, or reported value is embedded in the code.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import BinaryIO, TextIO

import pandas as pd


REPORT_NAME = "表06161601-產險財務業務指標"

REQUIRED_COLUMNS = {
    "年度",
    "季度",
    "公司名稱",
    "自留綜合率",
    "自留費用率",
    "自留滿期損失率",
}

METRIC_COLUMNS = {
    "自留綜合率": (
        "reported_combined_ratio",
        "Reported Combined Ratio",
    ),
    "自留費用率": (
        "reported_expense_ratio",
        "Expense Ratio",
    ),
    "自留滿期損失率": (
        "reported_loss_ratio",
        "Loss Ratio",
    ),
}

OUTPUT_COLUMNS = [
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

MAPPING_REQUIRED_COLUMNS = {
    "source_company_name",
    "company_id",
}


class TaiwanMetricsImportError(ValueError):
    """Raised when an uploaded file is not a supported indicator report."""


def _read_bytes(source: str | Path | bytes | BinaryIO | TextIO) -> bytes:
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
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise TaiwanMetricsImportError(
        "無法辨識 CSV 編碼；請從公開資訊網站重新下載 CSV 後再上傳。"
    )


def _find_header_row(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        normalized = {cell.strip() for cell in row}
        if REQUIRED_COLUMNS.issubset(normalized):
            return index

    missing = "、".join(sorted(REQUIRED_COLUMNS))
    raise TaiwanMetricsImportError(
        f"找不到財務業務指標欄位；檔案必須包含：{missing}。"
    )


def _to_number(series: pd.Series, column_name: str) -> pd.Series:
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

    Returned ratio values are numeric percentages, so ``88.87`` means
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
    """Convert the imported report to the app's long-form metric schema."""

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
    for source_column, (metric_id, metric_name) in METRIC_COLUMNS.items():
        frame = pd.DataFrame(
            {
                "roc_year": report["年度"],
                "calendar_year": report["年度"] + 1911,
                "quarter": report["季度"],
                "company_name": report["公司名稱"],
                "metric_id": metric_id,
                "metric_name": metric_name,
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
    metrics = metrics[OUTPUT_COLUMNS]
    return metrics.sort_values(
        ["calendar_year", "quarter", "company_name", "metric_id"],
        kind="stable",
    ).reset_index(drop=True)


def import_taiwan_reported_metrics(
    source: str | Path | bytes | BinaryIO | TextIO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return both the original wide report and standardized long metrics."""

    report = load_taiwan_indicator_report(source)
    metrics = to_standard_metrics(report)
    return report, metrics


def add_company_ids(
    metrics: pd.DataFrame,
    mapping_source: str | Path | bytes | BinaryIO | TextIO,
) -> pd.DataFrame:
    """Attach project company IDs using an external name-mapping CSV.

    Insurers not included in the mapping remain available in the imported
    report and receive an empty ``company_id``.
    """

    mapping_text = _decode_report(_read_bytes(mapping_source))
    mapping = pd.read_csv(
        io.StringIO(mapping_text),
        dtype="string",
    ).fillna("")
    mapping.columns = mapping.columns.str.strip()

    missing = MAPPING_REQUIRED_COLUMNS.difference(mapping.columns)
    if missing:
        raise TaiwanMetricsImportError(
            f"公司名稱對照檔缺少必要欄位：{'、'.join(sorted(missing))}"
        )

    mapping = mapping[
        ["source_company_name", "company_id"]
    ].copy()
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
    mapped["company_id"] = mapped["company_id"].fillna("")

    ordered_columns = [
        "company_id",
        *[column for column in mapped.columns if column != "company_id"],
    ]
    return mapped[ordered_columns]


def company_metric_summary(
    metrics: pd.DataFrame,
    company_name: str,
    *,
    calendar_year: int | None = None,
    quarter: int | None = None,
) -> pd.DataFrame:
    """Select one insurer and pivot its reported ratios for display or merging."""

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
    return summary
