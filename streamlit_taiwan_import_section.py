"""Streamlit section for importing Taiwan official non-life metrics.

The uploaded RPT-06161601 CSV is kept as a complete Taiwan-market dataset.
Mapped insurers are also converted to the project's 27-column comparison
schema, so the same records can later be combined with overseas disclosures.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.taiwan_reported_metrics import (
    TaiwanMetricsImportError,
    add_company_ids,
    company_metric_summary,
    import_taiwan_reported_metrics,
    to_comparison_records,
)


REPO_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = REPO_ROOT / "config"
TAIWAN_COMPANY_MAPPING_FILE = CONFIG_DIR / "taiwan_company_mapping.csv"
COMPANIES_FILE = CONFIG_DIR / "companies_2025.csv"

SUMMARY_COLUMNS = {
    "company_name": "公司名稱",
    "calendar_year": "年度",
    "quarter": "季度",
    "reported_combined_ratio": "Reported Combined Ratio (%)",
    "loss_ratio": "Loss Ratio (%)",
    "expense_ratio": "Expense Ratio (%)",
    "value_status": "資料狀態",
    "source_name": "資料來源",
    "validation_status": "驗證狀態",
}

IMPORT_DISPLAY_COLUMNS = {
    "company_id": "全球比較 company_id",
    "company_name": "公司名稱",
    "calendar_year": "年度",
    "quarter": "季度",
    "metric_id": "metric_id",
    "value": "數值",
    "unit": "單位",
    "period_basis": "年度基礎",
    "validation_status": "驗證狀態",
}


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    """Return an Excel-friendly UTF-8 CSV."""

    return frame.to_csv(index=False).encode("utf-8-sig")


def _period_label(report: pd.DataFrame) -> tuple[str, str, str]:
    """Return ROC-year, quarter, and filename labels for one upload."""

    roc_years = sorted(report["年度"].astype("int64").unique())
    quarters = sorted(report["季度"].astype("int64").unique())
    calendar_years = sorted((report["年度"].astype("int64") + 1911).unique())

    roc_year_text = "、".join(map(str, roc_years))
    quarter_text = "、".join(map(str, quarters))
    file_period = (
        "-".join(map(str, calendar_years))
        + "_q"
        + "-".join(map(str, quarters))
    )
    return roc_year_text, quarter_text, file_period


def _render_company_summary(metrics: pd.DataFrame) -> None:
    """Render the three official ratios for one selected insurer and period."""

    companies = sorted(metrics["company_name"].dropna().unique())
    years = sorted(metrics["calendar_year"].unique(), reverse=True)
    quarters = sorted(metrics["quarter"].unique(), reverse=True)

    filters = st.columns(3)
    with filters[0]:
        selected_company = st.selectbox(
            "選擇國內產險公司",
            companies,
            key="taiwan_insurer",
        )
    with filters[1]:
        selected_year = st.selectbox(
            "西元年度",
            years,
            key="taiwan_calendar_year",
        )
    with filters[2]:
        selected_quarter = st.selectbox(
            "季度",
            quarters,
            key="taiwan_quarter",
        )

    summary = company_metric_summary(
        metrics,
        selected_company,
        calendar_year=int(selected_year),
        quarter=int(selected_quarter),
    )

    missing = [
        column for column in SUMMARY_COLUMNS if column not in summary.columns
    ]
    if missing:
        raise TaiwanMetricsImportError(
            "公司指標摘要缺少欄位：" + "、".join(missing)
        )

    st.dataframe(
        summary[list(SUMMARY_COLUMNS)].rename(columns=SUMMARY_COLUMNS),
        hide_index=True,
        use_container_width=True,
    )


def _render_comparison_records(
    comparison_records: pd.DataFrame,
    file_period: str,
) -> None:
    """Render and provide the 27-column global-comparison records."""

    st.caption(
        "僅納入 taiwan_company_mapping.csv 已對照的公司；"
        "目前為國泰產險與富邦產險。"
    )
    st.dataframe(
        comparison_records,
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "下載 27 欄全球比較紀錄",
        data=_csv_bytes(comparison_records),
        file_name=f"taiwan_comparison_records_{file_period}.csv",
        mime="text/csv",
        key="download_taiwan_comparison_records",
    )


def _render_imported_metrics(
    metrics: pd.DataFrame,
    file_period: str,
) -> None:
    """Render and provide all imported Taiwan-market ratios."""

    st.caption(
        "這份長表保留上傳報表中的所有公司；未列入六家公司比較者，"
        "company_id 會保持空白。"
    )
    missing = [
        column
        for column in IMPORT_DISPLAY_COLUMNS
        if column not in metrics.columns
    ]
    if missing:
        raise TaiwanMetricsImportError(
            "台灣指標長表缺少欄位：" + "、".join(missing)
        )

    st.dataframe(
        metrics[list(IMPORT_DISPLAY_COLUMNS)].rename(
            columns=IMPORT_DISPLAY_COLUMNS
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "下載全部台灣官方指標長表",
        data=_csv_bytes(metrics),
        file_name=f"taiwan_reported_metrics_{file_period}.csv",
        mime="text/csv",
        key="download_taiwan_reported_metrics",
    )


def render_taiwan_import_section() -> pd.DataFrame | None:
    """Render the uploader and return 27-column comparison records."""

    st.subheader("國內產險官方財務業務指標")
    st.caption(
        "請上傳公開資訊網站匯出的「表06161601－產險財務業務指標」CSV。"
        "程式會自動讀取年度、季度與所有公司，不需修改程式碼。"
    )

    uploaded_file = st.file_uploader(
        "上傳產險財務業務指標 CSV",
        type=["csv"],
        key="taiwan_rpt_06161601",
    )

    if uploaded_file is None:
        st.info("尚未上傳國內產險財務業務指標總表。")
        return None

    missing_files = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in (TAIWAN_COMPANY_MAPPING_FILE, COMPANIES_FILE)
        if not path.is_file()
    ]
    if missing_files:
        st.error("缺少必要設定檔：" + "、".join(missing_files))
        return None

    try:
        report, metrics = import_taiwan_reported_metrics(uploaded_file)
        metrics = add_company_ids(metrics, TAIWAN_COMPANY_MAPPING_FILE)
        comparison_records = to_comparison_records(metrics, COMPANIES_FILE)
        roc_year_text, quarter_text, file_period = _period_label(report)
    except TaiwanMetricsImportError as error:
        st.error(f"匯入失敗：{error}")
        return None
    except (OSError, UnicodeError) as error:
        st.error(f"無法讀取上傳檔案或設定檔：{error}")
        return None

    mapped_company_ids = sorted(
        comparison_records["company_id"].drop_duplicates().tolist()
    )
    warning_count = int(
        comparison_records["validation_status"].eq("warning").sum()
    )

    st.success(
        f"匯入成功：民國 {roc_year_text} 年、第 {quarter_text} 季，"
        f"共 {len(report)} 家公司。"
    )

    summary_cards = st.columns(4)
    summary_cards[0].metric("官方報表公司", len(report))
    summary_cards[1].metric("匯入指標", len(metrics))
    summary_cards[2].metric("全球比較公司", len(mapped_company_ids))
    summary_cards[3].metric("27欄比較紀錄", len(comparison_records))

    st.caption(
        "已連接全球比較設定："
        + "、".join(mapped_company_ids)
        + f"；其中 {warning_count} 筆紀錄需複核。"
    )

    summary_tab, comparison_tab, all_metrics_tab = st.tabs(
        ["單一公司指標", "全球比較格式", "全部匯入資料"]
    )
    with summary_tab:
        _render_company_summary(metrics)
    with comparison_tab:
        _render_comparison_records(comparison_records, file_period)
    with all_metrics_tab:
        _render_imported_metrics(metrics, file_period)

    mismatch_companies = (
        metrics.loc[
            metrics["validation_status"].eq("ratio_mismatch"),
            "company_name",
        ]
        .drop_duplicates()
        .tolist()
    )
    if mismatch_companies:
        st.warning(
            f"{len(mismatch_companies)} 家公司的自留費用率加自留滿期損失率，"
            "與自留綜合率差異超過 0.02 個百分點。程式已保留官方原值，"
            "並在 27 欄紀錄標記為 warning。"
        )

    return comparison_records
