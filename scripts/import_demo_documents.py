"""Upload source files from the synthetic demo ZIP into the private Supabase bucket.

Run: python -m scripts.import_demo_documents path/to/Vendor_Onboarding_Synthetic_Demo_Data.zip
"""
from __future__ import annotations

import argparse
from pathlib import PurePosixPath
from zipfile import ZipFile

from dotenv import load_dotenv
from app import storage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", help="Path to the synthetic demo ZIP")
    args = parser.parse_args()
    load_dotenv()
    if not storage.configured():
        parser.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first")
    uploaded = skipped = 0
    with ZipFile(args.archive) as archive:
        for member in archive.infolist():
            parts = PurePosixPath(member.filename).parts
            if member.is_dir():
                continue
            if len(parts) == 5 and parts[1] == "cases" and parts[3] == "documents":
                key, filename = parts[2], parts[4]
                case_id = "SD-" + key
            elif len(parts) == 3 and parts[0] == "showcased_cases" and parts[2] not in {
                    "submitted_form.json", "expected_result.json"}:
                key, filename = parts[1], parts[2]
                case_id = key
            else:
                continue
            case = storage.find_case(case_id)
            if case is None:
                print(f"Skip {key}: no matching case in Supabase")
                skipped += 1
                continue
            if not any(doc["name"] == filename for doc in case["documents"]):
                print(f"Skip {key}/{filename}: no matching document record")
                skipped += 1
                continue
            if any(doc["name"] == filename and doc["available"] for doc in case["documents"]):
                skipped += 1
                continue
            storage.upload_document(key, filename, archive.read(member))
            uploaded += 1
            print(f"Stored {key}/{filename}")
    print(f"Uploaded {uploaded} files; skipped {skipped}.")


if __name__ == "__main__":
    main()
