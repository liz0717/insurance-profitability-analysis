"""Streamlit dashboard for the 2025 P&C insurer profitability project."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st


REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIG_DIR = REPO_ROOT / "config"
COMPANIES_FILE = CONFIG_DIR / "companies_2025.csv"
METRICS_FILE = CONFIG_DIR / "metrics_2025.csv"
SOURCES_FILE = CONFIG_DIR / "sources_2025.csv"


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    """Load one UTF-8 configuration CSV as text values."""

    return pd.read_csv(path, encoding="utf-8-sig", dtype="string").fillna("")


def load_project_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the three configuration tables displayed by the dashboard."""

    return (
        load_csv(COMPANIES_FILE),
        load_csv(METRICS_FILE),
        load_csv(SOURCES_FILE),
    )


def validate_project_configuration() -> dict[str, object]:
    """Import and run the configuration validator after page setup."""

    try:
        from src.validate_config import validate_configuration
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "找不到 src/validate_config.py 或其相依模組。"
        ) from exc

    return validate_configuration()


def render_validation_error(error: Exception) -> None:
    """Show a concise deployment/configuration error without a raw traceback."""

    st.error("設定檔檢查失敗，網站尚未載入資料。")
    st.write(
        "請確認 `config` 資料夾中的設定檔與 `src/validate_config.py` "
        "都已提交至目前部署分支。"
    )
    with st.expander("查看錯誤內容"):
        st.code(str(error) or error.__class__.__name__)


def render_summary(validation: dict[str, object]) -> None:
    """Display configuration coverage returned by the validator."""

    first_row = st.columns(4)
    first_row[0].metric("比較對象", validation.get("companies", 0))
    first_row[1].metric("比較指標", validation.get("metrics", 0))
    first_row[2].metric("標準輸出欄位", validation.get("output_fields", 0))
    first_row[3].metric("官方來源紀錄", validation.get("source_records", 0))

    second_row = st.columns(3)
    second_row[0].metric(
        "台灣公司對照",
        validation.get("taiwan_mapping_records", 0),
    )
    second_row[1].metric(
        "指標搜尋規則",
        validation.get("metric_rule_records", 0),
    )
    second_row[2].metric(
        "待補來源公司",
        validation.get("companies_without_sources", 0),
    )


def select_columns(
    frame: pd.DataFrame,
    columns: list[str],
    table_name: str,
) -> pd.DataFrame:
    """Select display columns and report a clear schema error."""

    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{table_name} 缺少欄位：{', '.join(missing)}")
    return frame[columns].copy()


def render_company_tab(companies: pd.DataFrame) -> None:
    """Render the six-company comparison scope."""

    st.subheader("2025年比較範圍")
    columns = [
        "display_name_zh",
        "display_name_en",
        "entity_type",
        "reporting_scope",
        "home_market",
        "reporting_currency",
        "accounting_basis",
        "source_status",
    ]
    labels = {
        "display_name_zh": "公司／市場",
        "display_name_en": "Company / Market",
        "entity_type": "實體類型",
        "reporting_scope": "比較範圍",
        "home_market": "主要市場",
        "reporting_currency": "報表幣別",
        "accounting_basis": "會計基礎",
        "source_status": "主要來源狀態",
    }
    display = select_columns(companies, columns, COMPANIES_FILE.name)
    st.dataframe(
        display.rename(columns=labels),
        hide_index=True,
        use_container_width=True,
    )


def render_metric_tab(metrics: pd.DataFrame) -> None:
    """Render the six standardized profitability and scale metrics."""

    st.subheader("獲利能力及規模指標")
    st.caption(
        "綜合率、損失率與費用率愈低愈佳；承保損益愈高愈佳。"
        "已賺保費或保險收入僅作規模參考，不進行排名。"
    )
    columns = [
        "display_name",
        "metric_category",
        "value_type",
        "default_unit",
        "default_adjustment_basis",
        "comparison_role",
        "ranking_direction",
    ]
    labels = {
        "display_name": "指標",
        "metric_category": "類別",
        "value_type": "數值類型",
        "default_unit": "預設單位",
        "default_adjustment_basis": "調整基礎",
        "comparison_role": "比較角色",
        "ranking_direction": "排序方向",
    }
    display = select_columns(metrics, columns, METRICS_FILE.name)
    st.dataframe(
        display.rename(columns=labels),
        hide_index=True,
        use_container_width=True,
    )


def render_source_tab(
    companies: pd.DataFrame,
    sources: pd.DataFrame,
    validation: dict[str, object],
) -> None:
    """Render official source coverage and review warnings."""

    st.subheader("官方資料來源")
    company_names = select_columns(
        companies,
        ["company_id", "display_name_zh", "display_name_en"],
        COMPANIES_FILE.name,
    )
    progress = sources.merge(
        company_names,
        on="company_id",
        how="left",
        validate="many_to_one",
    )
    columns = [
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
    progress = select_columns(progress, columns, SOURCES_FILE.name)
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

    missing_ids = validation.get("company_ids_without_sources", [])
    if isinstance(missing_ids, list) and missing_ids:
        missing_names = companies.loc[
            companies["company_id"].isin(missing_ids),
            "display_name_zh",
        ].tolist()
        st.warning("尚待補充官方來源：" + "、".join(missing_names))

    review_count = int(validation.get("sources_needing_review", 0))
    if review_count:
        st.info(f"目前有 {review_count} 筆來源仍需確認指標涵蓋範圍。")


def load_taiwan_renderer() -> Callable[[], pd.DataFrame | None]:
    """Load the Taiwan upload section while keeping other tabs available."""

    try:
        from streamlit_taiwan_import_section import (
            render_taiwan_import_section,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "找不到 streamlit_taiwan_import_section.py 或其相依模組。"
        ) from exc

    return render_taiwan_import_section


def render_taiwan_tab() -> None:
    """Render the Taiwan official-ratio uploader."""

    try:
        renderer = load_taiwan_renderer()
        renderer()
    except RuntimeError as exc:
        st.error("國內官方指標匯入模組尚未載入。")
        st.code(str(exc))


def main() -> None:
    """Run the Streamlit application."""

    st.set_page_config(
        page_title="全球產險公司獲利能力分析",
        page_icon="📊",
        layout="wide",
    )

    st.title("全球產險公司獲利能力分析")
    st.caption("Global P&C Insurance Profitability Analysis — 2025")
    st.markdown(
        """
本專案以公開財報比較六家產險公司或市場的保險本業獲利能力。
目前已建立統一設定、官方來源管理及台灣公開資訊匯入功能；
後續將接續通用財報擷取、六項指標比較表與原始證據追溯。
"""
    )

    try:
        validation = validate_project_configuration()
        companies, metrics, sources = load_project_tables()
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        render_validation_error(exc)
        return

    st.success("設定檔檢查成功")
    render_summary(validation)

    company_tab, metric_tab, source_tab, taiwan_tab = st.tabs(
        ["比較公司", "比較指標", "資料來源", "國內官方指標"]
    )

    try:
        with company_tab:
            render_company_tab(companies)
        with metric_tab:
            render_metric_tab(metrics)
        with source_tab:
            render_source_tab(companies, sources, validation)
        with taiwan_tab:
            render_taiwan_tab()
    except (KeyError, TypeError, ValueError) as exc:
        st.error("畫面資料欄位無法顯示，請重新檢查設定檔。")
        with st.expander("查看錯誤內容"):
            st.code(str(exc) or exc.__class__.__name__)


if __name__ == "__main__":
    main()
