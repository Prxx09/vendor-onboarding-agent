"""Render fictional text case documents to PDFs for the extraction pipeline."""

from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1] / "demo" / "cases"


def main() -> None:
    count = 0
    for source in ROOT.glob("*/documents/*.txt"):
        document = pymupdf.open()
        page = document.new_page()
        text = source.read_text(encoding="utf-8")
        page.insert_textbox(pymupdf.Rect(54, 54, 540, 780), text, fontsize=11, lineheight=1.5)
        target = source.with_suffix(".pdf")
        document.save(target)
        document.close()
        count += 1
    print(f"Generated {count} fictional demo PDFs under {ROOT}")


if __name__ == "__main__":
    main()
