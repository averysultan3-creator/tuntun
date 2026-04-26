"""Google API authentication via Service Account.

Setup:
  1. Go to console.cloud.google.com → Create project → Enable APIs:
     - Google Sheets API
     - Google Docs API
     - Google Drive API
  2. IAM & Admin → Service Accounts → Create → Download JSON key
  3. Save key to credentials/google_service_account.json
  4. Share your Spreadsheet/Drive folder with the service account email
  5. Set GOOGLE_SERVICE_ACCOUNT_FILE and GOOGLE_ENABLED=true in .env
"""
import logging
from pathlib import Path

_credentials = None
_authorized_http = None


def get_credentials():
    """Return google.oauth2.service_account.Credentials or None if not configured."""
    global _credentials
    if _credentials is not None:
        return _credentials

    try:
        import config
        if not config.GOOGLE_ENABLED:
            return None

        key_file = Path(config.GOOGLE_SERVICE_ACCOUNT_FILE)
        if not key_file.exists():
            logging.warning(
                "Google: service account file not found: %s — Google integration disabled",
                key_file,
            )
            return None

        from google.oauth2 import service_account

        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive",
        ]
        _credentials = service_account.Credentials.from_service_account_file(
            str(key_file), scopes=SCOPES
        )
        logging.info("Google: authenticated as %s", _credentials.service_account_email)
        return _credentials

    except ImportError:
        logging.warning("Google: google-auth not installed — run: pip install google-auth google-api-python-client")
        return None
    except Exception as e:
        logging.error("Google auth error: %s", e)
        return None


def is_google_enabled() -> bool:
    """Return True if Google integration is configured and credentials are available."""
    try:
        import config
        return bool(config.GOOGLE_ENABLED and get_credentials() is not None)
    except Exception:
        return False
