"""Export a stored onboarding report as standalone HTML."""

import argparse
import sys
from pathlib import Path

from app.repositories.factory import get_repository
from app.services.report_service import ReportService, export_html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id")
    parser.add_argument("--out", required=True, help="Destination HTML file path")
    args = parser.parse_args()
    try:
        report = ReportService(get_repository()).build_report(args.request_id)
        html = export_html(report)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - produce a concise CLI error
        print(f"Report export failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    print(f"Report exported successfully: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
