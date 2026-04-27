"""Google Memory Ingestion — TUNTUN Memory V2.

Reads from Google Sheets / Docs / Drive and indexes items
into memory_items (the unified brain-index) via memory_indexer.

Public API
──────────
ingest_sheet_rows(user_id, spreadsheet_id, sheet_name, limit) -> dict
ingest_doc_text(user_id, doc_id, doc_url, title, text)        -> int
ingest_drive_file(user_id, file_id, filename, url, ...)       -> int

All writes are idempotent (upsert by source_id/hash).
No real Google calls happen in tests — callers inject data directly.
"""
import logging
from typing import Optional

from bot.modules.memory_indexer import index_memory_item

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Sheet rows → memory_items
# ──────────────────────────────────────────────────────────────────────────────

async def ingest_sheet_rows(
    user_id: int,
    spreadsheet_id: str,
    sheet_name: str,
    limit: int = 200,
    rows: Optional[list[dict]] = None,
) -> dict:
    """Index rows from a Google Sheet into memory_items.

    If `rows` is provided (e.g. in tests), skip the real Sheets API call.
    Returns {"indexed": N, "skipped": N, "errors": N}.
    """
    report = {"indexed": 0, "skipped": 0, "errors": 0}

    if rows is None:
        # Real API path — guarded by try/except so callers never crash
        try:
            from bot.integrations.google.sheets import read_sheet
            rows = await read_sheet(spreadsheet_id, sheet_name, limit=limit)
        except Exception as exc:
            logger.warning(
                "ingest_sheet_rows: read_sheet failed user=%s sheet=%s: %s",
                user_id, sheet_name, exc,
            )
            return report

    if not rows:
        return report

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

    for idx, row in enumerate(rows):
        try:
            # Build content from all non-empty values
            parts = [f"{k}: {v}" for k, v in row.items() if v and str(v).strip()]
            content = "\n".join(parts)
            if not content.strip():
                report["skipped"] += 1
                continue

            # Use sheet_name + row index as source_id for deduplication
            # If the row has an "id" or "object_id" column, prefer that
            row_id = str(row.get("id") or row.get("object_id") or f"{sheet_name}_{idx}")
            source_id = f"{spreadsheet_id}:{sheet_name}:{row_id}"

            # Guess source_date from "date" column
            source_date = (
                str(row.get("date") or row.get("Date") or "")[:10] or None
            )

            rid = await index_memory_item(
                user_id=user_id,
                content=content,
                source_type="google_sheet_row",
                source_id=source_id,
                source_url=f"{sheet_url}",
                source_title=f"{sheet_name} (Google Sheets)",
                source_date=source_date,
                importance=2,
            )
            if rid:
                report["indexed"] += 1
            else:
                report["skipped"] += 1
        except Exception as exc:
            logger.warning(
                "ingest_sheet_rows: row %d error user=%s: %s", idx, user_id, exc
            )
            report["errors"] += 1

    return report


# ──────────────────────────────────────────────────────────────────────────────
# 2. Google Doc text → memory_items
# ──────────────────────────────────────────────────────────────────────────────

async def ingest_doc_text(
    user_id: int,
    doc_id: str,
    doc_url: str,
    title: str,
    text: Optional[str] = None,
) -> int:
    """Index a Google Doc into memory_items.

    If `text` is None, attempts a real Docs API read (stub-able in tests).
    Returns row_id (0 on failure or skip).
    """
    if text is None:
        try:
            text = await _read_doc_text(doc_id)
        except Exception as exc:
            logger.warning("ingest_doc_text: read failed doc_id=%s: %s", doc_id, exc)
            return 0

    if not text or not text.strip():
        return 0

    return await index_memory_item(
        user_id=user_id,
        content=text[:4000],  # cap to avoid huge records
        source_type="google_doc",
        source_id=doc_id,
        source_url=doc_url,
        source_title=title,
        importance=3,
    )


async def _read_doc_text(doc_id: str) -> str:
    """Read plain text from a Google Doc (synchronous API via asyncio executor)."""
    import asyncio

    def _sync_read():
        from bot.integrations.google.auth import get_credentials
        creds = get_credentials()
        if creds is None:
            return ""
        try:
            from googleapiclient.discovery import build
            svc = build("docs", "v1", credentials=creds, cache_discovery=False)
            doc = svc.documents().get(documentId=doc_id).execute()
            body = doc.get("body", {}).get("content", [])
            lines = []
            for elem in body:
                para = elem.get("paragraph")
                if para:
                    for pe in para.get("elements", []):
                        tr = pe.get("textRun")
                        if tr:
                            lines.append(tr.get("content", ""))
            return "".join(lines).strip()
        except Exception as e:
            logger.warning("_read_doc_text: %s", e)
            return ""

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_read)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Google Drive file metadata → memory_items
# ──────────────────────────────────────────────────────────────────────────────

async def ingest_drive_file(
    user_id: int,
    file_id: str,
    filename: str,
    url: str,
    mime_type: str = "",
    description: str = "",
    created_date: Optional[str] = None,
    importance: int = 2,
) -> int:
    """Index Drive file metadata into memory_items.

    Content is built from filename + description; no file download.
    """
    parts = [filename]
    if description:
        parts.append(description)
    if mime_type:
        parts.append(f"тип: {mime_type}")
    content = " — ".join(parts)

    return await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="google_drive_file",
        source_id=file_id,
        source_url=url,
        source_title=filename,
        source_date=created_date,
        importance=importance,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Convenience: ingest all important sheets for a user
# ──────────────────────────────────────────────────────────────────────────────

_IMPORTANT_SHEETS = ["Finance", "Memory", "Tasks", "Ideas", "LongNotes"]


async def ingest_all_sheets(user_id: int, spreadsheet_id: str) -> dict:
    """Ingest the most important sheets from a user's spreadsheet.

    Non-blocking for individual sheets — errors are logged, not raised.
    Returns aggregated report.
    """
    total = {"indexed": 0, "skipped": 0, "errors": 0}

    for sheet_name in _IMPORTANT_SHEETS:
        try:
            report = await ingest_sheet_rows(user_id, spreadsheet_id, sheet_name)
            for k in total:
                total[k] += report.get(k, 0)
        except Exception as exc:
            logger.warning(
                "ingest_all_sheets: sheet=%s user=%s error: %s",
                sheet_name, user_id, exc,
            )
            total["errors"] += 1

    return total
