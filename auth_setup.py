"""One-time OAuth token setup — run this interactively before the pipeline."""
import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
CLIENT_JSON = os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "oauth_client.json")
TOKEN_PATH  = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", ".gdrive-token.json")

print(f"Opening browser for Google OAuth...")
print(f"Client: {CLIENT_JSON}")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_JSON, SCOPES)
creds = flow.run_local_server(port=8765, open_browser=True)
Path(TOKEN_PATH).write_text(creds.to_json())
print(f"\n✅ Token saved to {TOKEN_PATH}")
print("You can now run: python3 pipeline.py scrape <url>")
