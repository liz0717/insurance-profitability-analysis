"""
通用財報文字擷取工具

功能：
1. 讀取 data/raw 內下載完成的財報。
2. 支援 PDF、HTML、CSV、Excel、TXT。
3. 將財報轉換成可搜尋的純文字。
4. 將文字檔儲存到 data/text。
5. 建立 data/text_manifest_2025.csv 擷取結果清單。

執行方式：
python src/extract_text.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader


# 專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 預設輸入與輸出位置
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "text"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "text_manifest_2025.csv"


def normalize_text(text: str) -> str:
    """
    清理擷取後的文字：
    1. 統一換行符號。
    2. 移除多餘空白。
    3. 保留段落結構。
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")

    cleaned_lines = []

    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 最多保留一個空白行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def detect_document_type(file_path: Path) -> Optional[str]:
    """
    根據副檔名或檔案內容判斷財報格式。
    """
    extension = file_path.suffix.lower()

    if extension == ".pdf":
        return "pdf"

    if extension in {".html", ".htm"}:
        return "html"

    if extension in {".csv", ".tsv"}:
        return "csv"

    if extension in {".xlsx", ".xls"}:
        return "excel"

    if extension in {".txt", ".text"}:
        return "text"

    # 財報網址可能沒有正確副檔名，因此進一步檢查檔案內容
    try:
        with file_path.open("rb") as file:
            header = file.read(4096)

        if header.startswith(b"%PDF"):
            return "pdf"

        lowered_header = header.lower()

        if (
            b"<!doctype html" in lowered_header
            or b"<html" in lowered_header
            or b"<body" in lowered_header
        ):
            return "html"

        # XLSX 本質上是 ZIP 格式
        if header.startswith(b"PK\x03\x04"):
            return "excel"

    except OSError:
        return None

    return None


def extract_pdf(file_path: Path) -> tuple[str, int]:
    """
    從 PDF 財報逐頁擷取文字。
    回傳：文字內容、頁數。
    """
    reader = PdfReader(str(file_path))
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as error:
            page_text = f"[第 {page_number} 頁擷取失敗：{error}]"

        pages.append(
            f"===== PAGE {page_number} =====\n{page_text}"
        )

    return "\n\n".join(pages), len(reader.pages)


def extract_html(file_path: Path) -> tuple[str, int]:
    """
    從 HTML 財報擷取可見文字。
    """
    raw_html = file_path.read_bytes()

    soup = BeautifulSoup(raw_html, "html.parser")

    # 移除不屬於財報正文的程式與樣式
    for tag in soup(
        ["script", "style", "noscript", "svg", "canvas"]
    ):
        tag.decompose()

    text = soup.get_text(separator="\n")

    return text, 1


def read_csv_with_fallback(file_path: Path) -> pd.DataFrame:
    """
    使用常見編碼讀取 CSV，避免不同國家財報產生亂碼。
    """
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
    last_error = None

    for encoding in encodings:
        try:
            return pd.read_csv(
                file_path,
                sep=None,
                engine="python",
                dtype=str,
                encoding=encoding,
                keep_default_na=False,
            )
        except Exception as error:
            last_error = error

    raise ValueError(
        f"無法讀取 CSV：{last_error}"
    )


def dataframe_to_text(
    dataframe: pd.DataFrame,
    section_name: str,
) -> str:
    """
    將表格轉換成容易搜尋的逐列文字。
    """
    dataframe = dataframe.fillna("").astype(str)

    lines = [f"===== {section_name} ====="]

    if dataframe.empty:
        lines.append("[空白表格]")
        return "\n".join(lines)

    columns = [str(column) for column in dataframe.columns]
    lines.append("欄位：" + " | ".join(columns))

    for row_number, row in dataframe.iterrows():
        values = []

        for column in dataframe.columns:
            value = str(row[column]).strip()

            if value:
                values.append(f"{column}: {value}")

        if values:
            lines.append(
                f"ROW {row_number + 1} | " + " | ".join(values)
            )

    return "\n".join(lines)


def extract_csv(file_path: Path) -> tuple[str, int]:
    """
    從 CSV 或 TSV 財報擷取文字。
    """
    dataframe = read_csv_with_fallback(file_path)
    text = dataframe_to_text(
        dataframe,
        section_name=file_path.name,
    )

    return text, 1


def extract_excel(file_path: Path) -> tuple[str, int]:
    """
    從 Excel 財報擷取所有工作表內容。
    """
    workbook = pd.ExcelFile(file_path)
    sections = []

    for sheet_name in workbook.sheet_names:
        dataframe = pd.read_excel(
            workbook,
            sheet_name=sheet_name,
            dtype=str,
            keep_default_na=False,
        )

        sections.append(
            dataframe_to_text(
                dataframe,
                section_name=f"SHEET: {sheet_name}",
            )
        )

    return "\n\n".join(sections), len(workbook.sheet_names)


def extract_plain_text(file_path: Path) -> tuple[str, int]:
    """
    讀取純文字格式財報。
    """
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
    last_error = None

    for encoding in encodings:
        try:
            text = file_path.read_text(encoding=encoding)
            return text, 1
        except Exception as error:
            last_error = error

    raise ValueError(
        f"無法讀取文字檔：{last_error}"
    )


def extract_document(
    file_path: Path,
    document_type: str,
) -> tuple[str, int]:
    """
    根據財報格式選擇對應的文字擷取方法。
    """
    if document_type == "pdf":
        return extract_pdf(file_path)

    if document_type == "html":
        return extract_html(file_path)

    if document_type == "csv":
        return extract_csv(file_path)

    if document_type == "excel":
        return extract_excel(file_path)

    if document_type == "text":
        return extract_plain_text(file_path)

    raise ValueError(
        f"尚未支援的財報格式：{document_type}"
    )


def create_output_path(
    source_file: Path,
    input_dir: Path,
    output_dir: Path,
) -> Path:
    """
    保留原始資料夾結構，建立對應的 TXT 輸出位置。
    """
    relative_path = source_file.relative_to(input_dir)
    output_path = output_dir / relative_path
    output_path = output_path.with_suffix(".txt")

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return output_path


def process_documents(
    input_dir: Path,
    output_dir: Path,
    manifest_path: Path,
) -> pd.DataFrame:
    """
    批次處理所有下載完成的財報。
    """
    if not input_dir.exists():
        raise FileNotFoundError(
            f"找不到財報下載資料夾：{input_dir}\n"
            "請先執行 python src/fetch_sources.py"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    results = []

    source_files = sorted(
        file_path
        for file_path in input_dir.rglob("*")
        if file_path.is_file()
    )

    if not source_files:
        print(f"⚠️ {input_dir} 內沒有可處理的財報檔案。")
        return pd.DataFrame()

    print(f"找到 {len(source_files)} 個檔案。")
    print("-" * 60)

    for index, source_file in enumerate(source_files, start=1):
        relative_source = source_file.relative_to(PROJECT_ROOT)
        document_type = detect_document_type(source_file)

        print(
            f"[{index}/{len(source_files)}] "
            f"處理：{relative_source}"
        )

        if document_type is None:
            print("  ⚠️ 略過：無法判斷或尚未支援的檔案格式")

            results.append(
                {
                    "source_file": str(relative_source),
                    "text_file": "",
                    "document_type": "unknown",
                    "status": "skipped",
                    "character_count": 0,
                    "page_or_sheet_count": 0,
                    "error_message": "無法判斷或尚未支援的檔案格式",
                }
            )
            continue

        try:
            raw_text, page_or_sheet_count = extract_document(
                source_file,
                document_type,
            )

            cleaned_text = normalize_text(raw_text)

            if not cleaned_text:
                raise ValueError(
                    "未擷取到文字，PDF 可能是掃描影像格式"
                )

            output_path = create_output_path(
                source_file=source_file,
                input_dir=input_dir,
                output_dir=output_dir,
            )

            output_path.write_text(
                cleaned_text,
                encoding="utf-8",
            )

            relative_output = output_path.relative_to(PROJECT_ROOT)

            results.append(
                {
                    "source_file": str(relative_source),
                    "text_file": str(relative_output),
                    "document_type": document_type,
                    "status": "success",
                    "character_count": len(cleaned_text),
                    "page_or_sheet_count": page_or_sheet_count,
                    "error_message": "",
                }
            )

            print(
                f"  ✅ 完成：{relative_output} "
                f"({len(cleaned_text):,} 字元)"
            )

        except Exception as error:
            results.append(
                {
                    "source_file": str(relative_source),
                    "text_file": "",
                    "document_type": document_type,
                    "status": "failed",
                    "character_count": 0,
                    "page_or_sheet_count": 0,
                    "error_message": str(error),
                }
            )

            print(f"  ❌ 失敗：{error}")

    manifest = pd.DataFrame(results)

    manifest.to_csv(
        manifest_path,
        index=False,
        encoding="utf-8-sig",
    )

    return manifest


def print_summary(
    manifest: pd.DataFrame,
    manifest_path: Path,
) -> None:
    """
    顯示文字擷取執行結果摘要。
    """
    if manifest.empty:
        return

    success_count = int(
        (manifest["status"] == "success").sum()
    )
    failed_count = int(
        (manifest["status"] == "failed").sum()
    )
    skipped_count = int(
        (manifest["status"] == "skipped").sum()
    )

    print("\n" + "=" * 60)
    print("財報文字擷取完成")
    print("=" * 60)
    print(f"成功：{success_count} 個")
    print(f"失敗：{failed_count} 個")
    print(f"略過：{skipped_count} 個")
    print(f"結果清單：{manifest_path.relative_to(PROJECT_ROOT)}")


def parse_arguments() -> argparse.Namespace:
    """
    允許在 Colab 或本機指定不同的輸入、輸出位置。
    """
    parser = argparse.ArgumentParser(
        description="將下載完成的財報轉換成純文字。"
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="下載完成的財報資料夾",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="純文字輸出資料夾",
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="文字擷取結果清單",
    )

    return parser.parse_args()


def main() -> int:
    """
    程式主要執行入口。
    """
    args = parse_arguments()

    try:
        manifest = process_documents(
            input_dir=args.input_dir.resolve(),
            output_dir=args.output_dir.resolve(),
            manifest_path=args.manifest.resolve(),
        )

        print_summary(
            manifest=manifest,
            manifest_path=args.manifest.resolve(),
        )

        return 0

    except Exception as error:
        print(f"❌ 財報文字擷取失敗：{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
