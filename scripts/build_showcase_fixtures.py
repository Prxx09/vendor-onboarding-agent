"""Generate source documents for the four UI showcase cases.

Output can be added to the synthetic demo pack and uploaded with the
import_demo_documents.py script. All data is fictional.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.data import list_cases


def pdf_bytes(title: str, lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(48, 790, title)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(48, 772, "SYNTHETIC TEST DOCUMENT - NOT FOR REAL VENDOR DECISIONS")
    y = 740
    for line in lines:
        if y < 80:
            pdf.showPage()
            y = 780
        pdf.setFont("Helvetica", 10)
        pdf.drawString(48, y, line[:110])
        y -= 23
    pdf.save()
    return buffer.getvalue()


def form_lines(case: dict) -> list[str]:
    f = case["submitted_form"]
    return [
        f"Case ID: {case['id']}",
        f"Legal name: {f['legal_name']}",
        f"Category: {case['category']}",
        f"Tax ID / GSTIN: {f['tax_id']}",
        f"PAN: {f['pan']}",
        f"Bank account: {f['bank_account']}",
        f"IFSC: {f['ifsc']}",
        f"Registered address: {f['registered_address']}",
        f"Contact email: {f['contact_email']}",
        f"Submitted by: {case['submitted_by']}",
        f"Submitted at (UTC): {case['submitted_at']}",
    ]


def blurred_cheque() -> bytes:
    image = Image.new("RGB", (1050, 380), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 1030, 360), outline="#708090", width=3)
    draw.text((50, 75), "SYNTHETIC CANCELLED CHEQUE", fill="#333333")
    draw.text((50, 155), "Northstar Facility Services", fill="#333333")
    draw.text((50, 225), "Account  XXXXXX9012", fill="#333333")
    image = image.filter(ImageFilter.GaussianBlur(radius=3))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for case in list_cases():
        folder = output / case["id"]
        folder.mkdir(exist_ok=True)
        source = folder / case["document"]
        lines = form_lines(case)
        if case["id"] == "VO-1002":
            with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("vendor_intake.pdf", pdf_bytes("Vendor intake form", lines))
                archive.writestr("cancelled_cheque_low_quality.png", blurred_cheque())
                archive.writestr("README.txt", "MSME certificate intentionally absent. Safety declaration requires confirmation.\n")
        else:
            if case["id"] == "VO-1001":
                lines += ["Business registration: provided and legible.",
                          "Tax certificate: provided.", "Bank evidence: provided.",
                          "Compliance declarations: accepted."]
            elif case["id"] == "VO-1003":
                lines += ["Business registration: provided.", "Tax certificate: provided.",
                          "Bank evidence: provided.", "Security policy acknowledgement: accepted."]
            elif case["id"] == "VO-1004":
                lines += ["Registration proof: unreadable scan; replacement required.",
                          "Tax identifier: fails validation in this synthetic scenario.",
                          "Bank letter holder: Metro Office Traders (name mismatch).",
                          "Mandatory compliance declarations: missing."]
            source.write_bytes(pdf_bytes("Vendor onboarding source", lines))
        (folder / "submitted_form.json").write_text(
            json.dumps(case["submitted_form"], indent=2) + "\n", encoding="utf-8")
        (folder / "expected_result.json").write_text(
            json.dumps({"case_id": case["id"], "status": case["status"],
                        "confidence": case["confidence"], "checks": case["checks"]}, indent=2) + "\n",
            encoding="utf-8")
    print(f"Generated four showcase fixtures in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
