"""Drop-in Streamlit section for app.py.

Move the import statement and the code inside ``render_taiwan_import_section``
into the existing app, or import and call the function directly.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.taiwan_reported_metrics import (
    TaiwanMetricsImportError,
    company_metric_summary,
    import_taiwan_reported_metrics,
)


def render_taiwan_import_section() -> pd.DataFrame | None:
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

    try:
        report, metrics = import_taiwan_reported_metrics(uploaded_file)
    except TaiwanMetricsImportError as error:
        st.error(f"匯入失敗：{error}")
        return None

    roc_years = sorted(report["年度"].unique())
    quarters = sorted(report["季度"].unique())
    roc_year_text = "、".join(map(str, roc_years))
    quarter_text = "、".join(map(str, quarters))
    st.success(
        f"匯入成功：民國 {roc_year_text} 年、第 {quarter_text} 季，"
        f"共 {len(report)} 家公司。"
    )

    companies = sorted(report["公司名稱"].dropna().unique())
    selected_company = st.selectbox(
        "選擇國內產險公司",
        companies,
        key="taiwan_insurer",
    )
    selected_year = st.selectbox(
        "西元年度",
        sorted(metrics["calendar_year"].unique(), reverse=True),
        key="taiwan_calendar_year",
    )
    selected_quarter = st.selectbox(
        "季度",
        sorted(metrics["quarter"].unique(), reverse=True),
        key="taiwan_quarter",
    )

    summary = company_metric_summary(
        metrics,
        selected_company,
        calendar_year=int(selected_year),
        quarter=int(selected_quarter),
    )

    display_columns = {
        "company_name": "公司名稱",
        "calendar_year": "年度",
        "quarter": "季度",
        "reported_combined_ratio": "Reported Combined Ratio (%)",
        "reported_loss_ratio": "Loss Ratio (%)",
        "reported_expense_ratio": "Expense Ratio (%)",
        "value_status": "資料狀態",
        "source_name": "資料來源",
        "validation_status": "驗證狀態",
    }
    st.dataframe(
        summary[list(display_columns)].rename(columns=display_columns),
        hide_index=True,
        use_container_width=True,
    )

    if (metrics["validation_status"] == "ratio_mismatch").any():
        st.warning(
            "部分公司的自留費用率加自留滿期損失率，與自留綜合率不一致；"
            "程式保留官方原值並標記待檢查，不會自行覆蓋。"
        )

    return metrics
