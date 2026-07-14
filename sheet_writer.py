"""
sheet_writer.py — Write scraped listings to Google Sheets + upload images to Drive.

Sheet schema (one row per listing):
  - Identity + content fields
  - Ratings (overall + 6 sub-scores)
  - Amenity counts + gap list
  - Image metadata (count, room types, Drive folder URL)
  - Occupancy signal
  - ML columns (pre-wired, filled by downstream processes)
  - Strategy snapshot (what rules were applied when this row was written)

Intra-process learning:
  - Emits signal on write cost/time
  - Reads strategy to decide column ordering (priority fields first)

Inter-process contributions:
  - Image Drive URLs available to Generator (can embed in output PDFs)
  - Amenity gaps visible to Generator immediately
  - Occupancy % visible to Analyzer as ground truth

Usage:
  from sheet_writer import SheetWriter
  writer = SheetWriter()
  writer.write(listing_dict)             # single listing
  writer.write_batch(listings)          # multiple
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

import learning_store as ls

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SHEETS_ID        = os.getenv("GOOGLE_SHEETS_ID", "")
DRIVE_FOLDER_ID  = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
OAUTH_CLIENT_JSON = os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "")
TOKEN_PATH       = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", ".gdrive-token.json")
SHEET_NAME       = "ListingBoost_Scrapes"

# Column definitions — order matters for the spreadsheet
COLUMNS = [
    # A — Identity
    ("listing_id",            "Listing ID"),
    ("url",                   "URL"),
    ("scraped_at",            "Scraped At"),

    # D — Content
    ("title",                 "Title"),
    ("description",           "Description"),
    ("seo_title",             "SEO Title"),
    ("meta_description",      "Meta Description"),
    ("sub_description",       "Sub Description"),

    # I — Property
    ("property_type",         "Property Type"),
    ("room_type",             "Room Type"),
    ("person_capacity",       "Capacity"),
    ("min_nights",            "Min Nights"),
    ("max_nights",            "Max Nights"),

    # N — Location
    ("location",              "Location"),
    ("location_subtitle",     "Location Subtitle"),
    ("latitude",              "Latitude"),
    ("longitude",             "Longitude"),

    # R — Ratings
    ("rating_overall",        "Rating Overall"),
    ("rating_accuracy",       "Rating Accuracy"),
    ("rating_checkin",        "Rating Checkin"),
    ("rating_cleanliness",    "Rating Cleanliness"),
    ("rating_communication",  "Rating Communication"),
    ("rating_location",       "Rating Location"),
    ("rating_value",          "Rating Value"),
    ("review_count",          "Review Count"),

    # Z — Host
    ("host_name",             "Host Name"),
    ("host_is_superhost",     "Superhost"),
    ("host_is_verified",      "Verified"),
    ("host_years",            "Host Years"),
    ("host_rating_avg",       "Host Rating Avg"),
    ("host_review_count",     "Host Review Count"),

    # AF — Amenities
    ("amenities_available_count", "Amenities Available"),
    ("amenities_missing_count",   "Amenities Missing"),
    ("amenities_available",       "Amenities List (JSON)"),
    ("amenities_missing",         "Amenity Gaps (JSON)"),

    # AJ — Images
    ("image_total_count",     "Image Count"),
    ("drive_folder_url",      "Drive Folder URL"),   # filled by sheet_writer
    ("images_by_room_json",   "Images by Room (JSON)"),

    # AM — Availability
    ("occupancy_pct",         "Occupancy % (3mo)"),
    ("calendar_days",         "Calendar Days Scraped"),
    ("check_in_time",         "Check-in Date"),
    ("check_out_time",        "Check-out Date"),

    # AQ — ML Columns (pre-wired)
    ("ml_title_score",          "ML: Title Score"),
    ("ml_desc_score",           "ML: Desc Score"),
    ("ml_amenity_gap_score",    "ML: Amenity Gap Score"),
    ("ml_image_quality_score",  "ML: Image Quality Score"),
    ("ml_occupancy_predicted",  "ML: Predicted Occupancy"),
    ("ml_generated_title",      "ML: Generated Title"),
    ("ml_generated_desc",       "ML: Generated Description"),
    ("ml_outcome_delta",        "ML: Outcome Delta"),
    ("ml_client_feedback",      "ML: Client Feedback"),
    ("ml_version",              "ML: Version"),

    # AZ — Strategy snapshot
    ("strategy_snapshot_json",  "Strategy Snapshot (JSON)"),
]

COL_KEYS   = [c[0] for c in COLUMNS]
COL_LABELS = [c[1] for c in COLUMNS]


class SheetWriter:
    def __init__(self):
        self._creds  = None
        self._sheets = None
        self._drive  = None
        self._ensure_sheet_exists()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_creds(self) -> Credentials:
        if self._creds and self._creds.valid:
            return self._creds
        token_path = Path(TOKEN_PATH)
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and creds.valid:
            self._creds = creds
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            self._creds = creds
            return creds
        flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_JSON, SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
        self._creds = creds
        return creds

    def _get_sheets(self):
        if not self._sheets:
            self._sheets = build("sheets", "v4", credentials=self._get_creds())
        return self._sheets

    def _get_drive(self):
        if not self._drive:
            self._drive = build("drive", "v3", credentials=self._get_creds())
        return self._drive

    # ------------------------------------------------------------------
    # Sheet bootstrap
    # ------------------------------------------------------------------

    def _ensure_sheet_exists(self):
        """Create the sheet tab and header row if not already present."""
        try:
            sheets = self._get_sheets().spreadsheets()
            meta = sheets.get(spreadsheetId=SHEETS_ID).execute()
            existing = [s["properties"]["title"] for s in meta.get("sheets", [])]

            if SHEET_NAME not in existing:
                sheets.batchUpdate(
                    spreadsheetId=SHEETS_ID,
                    body={"requests": [{"addSheet": {"properties": {"title": SHEET_NAME}}}]}
                ).execute()
                print(f"[sheet_writer] Created sheet tab: {SHEET_NAME}")

            # Check if header row exists
            result = sheets.values().get(
                spreadsheetId=SHEETS_ID,
                range=f"{SHEET_NAME}!A1:A1"
            ).execute()

            if not result.get("values"):
                sheets.values().update(
                    spreadsheetId=SHEETS_ID,
                    range=f"{SHEET_NAME}!A1",
                    valueInputOption="RAW",
                    body={"values": [COL_LABELS]}
                ).execute()
                print(f"[sheet_writer] Header row written ({len(COL_LABELS)} columns)")
        except Exception as e:
            print(f"[sheet_writer] Warning: sheet bootstrap failed: {e}")

    # ------------------------------------------------------------------
    # Drive: folder + image upload
    # ------------------------------------------------------------------

    def _get_or_create_drive_folder(self, listing_id: str) -> tuple[str, str]:
        """Create /ListingBoost/{listing_id}/ in Drive. Returns (folder_id, web_url)."""
        drive = self._get_drive()

        # Find or create ListingBoost root
        lb_root_id = self._find_or_create_folder("ListingBoost", DRIVE_FOLDER_ID, drive)

        # Find or create listing subfolder
        listing_folder_id = self._find_or_create_folder(listing_id, lb_root_id, drive)
        web_url = f"https://drive.google.com/drive/folders/{listing_folder_id}"
        return listing_folder_id, web_url

    def _find_or_create_folder(self, name: str, parent_id: str, drive) -> str:
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        results = drive.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        folder = drive.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.folder",
                  "parents": [parent_id]},
            fields="id"
        ).execute()
        return folder["id"]

    def _upload_images(self, listing: dict, folder_id: str):
        """Download images from Airbnb CDN and upload to Drive, organized by room type."""
        drive = self._get_drive()
        images_by_room: dict[str, list[str]] = listing.get("images_by_room", {})
        total = sum(len(urls) for urls in images_by_room.values())
        uploaded = 0

        for room_type, urls in images_by_room.items():
            # Sub-folder per room type
            room_folder_id = self._find_or_create_folder(
                _safe_folder_name(room_type), folder_id, drive
            )

            for idx, img_url in enumerate(urls, 1):
                try:
                    img_data = _download_image(img_url)
                    if not img_data:
                        continue
                    filename = f"{_safe_folder_name(room_type)}_{idx:02d}.jpg"
                    media = MediaIoBaseUpload(BytesIO(img_data), mimetype="image/jpeg")
                    drive.files().create(
                        body={"name": filename, "parents": [room_folder_id]},
                        media_body=media,
                        fields="id"
                    ).execute()
                    uploaded += 1
                except Exception as e:
                    print(f"  [drive] Failed to upload {room_type} image {idx}: {e}")

        ls.emit("scraper", "images_uploaded", uploaded,
                {"listing_id": listing.get("listing_id"), "total": total})
        print(f"  [drive] Uploaded {uploaded}/{total} images")

    # ------------------------------------------------------------------
    # Sheet: append row
    # ------------------------------------------------------------------

    def _listing_to_row(self, listing: dict, drive_folder_url: str) -> list[Any]:
        """Map listing dict → ordered list of cell values matching COLUMNS."""
        # Augment listing with drive URL and JSON-serialized nested fields
        augmented = dict(listing)
        augmented["drive_folder_url"]      = drive_folder_url
        augmented["images_by_room_json"]   = json.dumps(listing.get("images_by_room", {}))
        augmented["amenities_available"]   = json.dumps(listing.get("amenities_available", []))
        augmented["amenities_missing"]     = json.dumps(listing.get("amenities_missing", []))
        augmented["strategy_snapshot_json"] = json.dumps(listing.get("strategy_snapshot", {}))

        return [_to_cell(augmented.get(key)) for key in COL_KEYS]

    def _append_row(self, row: list[Any]):
        self._get_sheets().spreadsheets().values().append(
            spreadsheetId=SHEETS_ID,
            range=f"{SHEET_NAME}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]}
        ).execute()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, listing: dict) -> str:
        """Write one listing: upload images to Drive, append row to Sheet. Returns Drive URL."""
        t0 = time.time()
        lid = listing.get("listing_id", "unknown")
        print(f"[sheet_writer] Writing listing {lid}...")

        # 1. Create Drive folder + upload images
        folder_id, folder_url = self._get_or_create_drive_folder(lid)
        print(f"  [drive] Folder: {folder_url}")
        self._upload_images(listing, folder_id)

        # 2. Append sheet row
        row = self._listing_to_row(listing, folder_url)
        self._append_row(row)
        elapsed = time.time() - t0

        ls.emit("sheet_writer", "write_time_secs", elapsed, {"listing_id": lid})
        ls.emit("sheet_writer", "write_success", 1, {"listing_id": lid})
        print(f"[sheet_writer] Done in {elapsed:.1f}s — {folder_url}")
        return folder_url

    def write_batch(self, listings: list[dict]) -> list[str]:
        """Write multiple listings. Returns list of Drive folder URLs."""
        urls = []
        for i, listing in enumerate(listings, 1):
            print(f"\n[sheet_writer] [{i}/{len(listings)}]")
            try:
                url = self.write(listing)
                urls.append(url)
            except Exception as e:
                lid = listing.get("listing_id", "?")
                print(f"[sheet_writer] ERROR on {lid}: {e}")
                ls.emit("sheet_writer", "write_error", None, {"listing_id": lid, "error": str(e)})
                urls.append("")
        return urls


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_folder_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\- ]", "", name).strip().replace(" ", "_")[:40]


def _to_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _download_image(url: str, timeout: int = 15) -> bytes | None:
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Write scraped listing to Google Sheets + Drive")
    parser.add_argument("json_file", help="Path to JSON file from scraper.py")
    args = parser.parse_args()

    data = json.loads(Path(args.json_file).read_text())
    if isinstance(data, dict):
        data = [data]

    writer = SheetWriter()
    urls = writer.write_batch(data)
    for url in urls:
        if url:
            print(f"  → {url}")
