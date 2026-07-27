"""Streamlit dashboard for the 2025 P&C insurer profitability project."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st


REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.validate_config import validate_configuration


CONFIG_DIR = REPO_ROOT / "config"
COMPANIES_FILE = CONFIG_DIR / "companies_2025.csv"
METRICS_FILE = CONFIG_DIR / "metrics_2025.csv"


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    """Load a UTF-8 configuration CSV."""

    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


st.set_page_config(
    page_title="全球產險公司獲利能力分析",
    page_icon="📊",
    layout="wide",
)

st.title("全球產險公司獲利能力分析")
st.caption("Global P&C Insurance Profitability Analysis — 2025")

st.markdown(
    """
本專案以公開財報比較六家產險公司或市場的核保獲利能力。
目前版本先檢查公司、指標及輸出欄位設定；後續將加入財報擷取結果、
比較表、圖表及原始證據。
"""
)

try:
    validation = validate_configuration()
except Exception as exc:
    st.error("設定檔檢查失敗。")
    st.exception(exc)
    st.stop()

st.success("設定檔檢查成功")

summary_columns = st.columns(4)
summary_columns[0].metric("比較對象", validation["companies"])
summary_columns[1].metric("比較指標", validation["metrics"])
summary_columns[2].metric("輸出欄位", validation["output_fields"])
summary_columns[3].metric(
    "待確認財報",
    validation["source_documents_pending"],
)

companies = load_csv(COMPANIES_FILE)
metrics = load_csv(METRICS_FILE)

company_tab, metric_tab, progress_tab = st.tabs(
    ["比較公司", "比較指標", "資料進度"]
)

with company_tab:
    st.subheader("2025年比較範圍")
    company_columns = [
        "display_name_zh",
        "display_name_en",
        "entity_type",
        "reporting_scope",
        "home_market",
        "reporting_currency",
    ]
    st.dataframe(
        companies[company_columns],
        hide_index=True,
        use_container_width=True,
    )

with metric_tab:
    st.subheader("獲利能力及規模指標")
    metric_columns = [
        "display_name",
        "metric_category",
        "value_type",
        "default_unit",
        "year_basis_required",
        "comparison_role",
        "ranking_direction",
    ]
    st.dataframe(
        metrics[metric_columns],
        hide_index=True,
        use_container_width=True,
    )

with progress_tab:
    st.subheader("官方財報蒐集進度")
    progress = companies[
        [
            "display_name_zh",
            "display_name_en",
            "fiscal_year",
            "source_status",
            "annual_report_url",
        ]
    ].copy()
    progress.columns = [
        "公司",
        "Company",
        "年度",
        "狀態",
        "官方財報網址",
    ]
    st.dataframe(
        progress,
        hide_index=True,
        use_container_width=True,
    )
    st.info("下一階段將逐家公司確認2025年官方財報及會計口徑。")
