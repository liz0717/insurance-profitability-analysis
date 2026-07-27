檔案庫
/
app.py


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
SOURCES_FILE = CONFIG_DIR / "sources_2025.csv"


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
目前版本先檢查公司、指標、來源及輸出欄位設定；後續將加入通用財報擷取流程、
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

summary_columns = st.columns(5)
summary_columns[0].metric("比較對象", validation["companies"])
summary_columns[1].metric("比較指標", validation["metrics"])
summary_columns[2].metric("輸出欄位", validation["output_fields"])
summary_columns[3].metric("來源紀錄", validation["source_records"])
summary_columns[4].metric("待補來源公司", validation["companies_without_sources"])

companies = load_csv(COMPANIES_FILE)
metrics = load_csv(METRICS_FILE)
sources = load_csv(SOURCES_FILE)

company_tab, metric_tab, progress_tab = st.tabs(
    ["比較公司", "比較指標", "資料來源"]
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
    st.subheader("官方資料來源")

    company_names = companies[
        ["company_id", "display_name_zh", "display_name_en"]
    ]
    progress = sources.merge(
        company_names,
        on="company_id",
        how="left",
        validate="many_to_one",
    )
    progress = progress[
        [
            "display_name_zh",
            "display_name_en",
            "source_title",
            "source_type",
            "reporting_period",
            "reporting_scope",
            "currency",
            "monetary_scale",
            "source_status",
            "source_url",
        ]
    ].copy()
    progress.columns = [
        "公司",
        "Company",
        "來源名稱",
        "格式",
        "年度",
        "範圍",
        "幣別",
        "單位",
        "狀態",
        "官方網址",
    ]

    st.dataframe(
        progress,
        hide_index=True,
        use_container_width=True,
        column_config={
            "官方網址": st.column_config.LinkColumn(
                "官方網址",
                display_text="開啟來源",
            )
        },
    )

    if validation["companies_without_sources"]:
        missing_names = companies.loc[
            companies["company_id"].isin(validation["company_ids_without_sources"]),
            "display_name_zh",
        ].tolist()
        st.warning("尚待補充官方來源：" + "、".join(missing_names))

    if validation["sources_needing_review"]:
        st.info(
            f"目前有 {validation['sources_needing_review']} 筆來源仍需確認指標涵蓋範圍。"
        )
