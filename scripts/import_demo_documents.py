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
            if member.is_dir() or len(parts) != 5 or parts[1] != "cases" or parts[3] != "documents":
                continue
            key, filename = parts[2], parts[4]
            case = storage.find_case("SD-" + key)
            if case is None:
                print(f"Skip {key}: no matching case in Supabase")
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
