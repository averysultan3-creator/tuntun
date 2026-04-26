"""Google Docs integration for TUNTUN — create and update documents."""
import logging
from typing import Optional


def _get_service():
    from bot.integrations.google.auth import get_credentials
    creds = get_credentials()
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build
        return build("docs", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        logging.error("Google Docs: failed to build service: %s", e)
        return None


def _get_drive_service():
    from bot.integrations.google.auth import get_credentials
    creds = get_credentials()
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logging.error("Google Drive (for Docs): failed to build service: %s", e)
        return None


def get_doc_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}"


def _create_doc_sync(title: str, content: str, folder_id: str = None) -> Optional[str]:
    """Create a Google Doc and return its ID."""
    docs_svc = _get_service()
    drive_svc = _get_drive_service()
    if not docs_svc or not drive_svc:
        return None
    try:
        # Create empty doc
        doc = docs_svc.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        # Write content
        if content:
            requests = [{"insertText": {"location": {"index": 1}, "text": content}}]
            docs_svc.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

        # Move to folder if specified
        if folder_id:
            file_meta = drive_svc.files().get(fileId=doc_id, fields="parents").execute()
            prev_parents = ",".join(file_meta.get("parents", []))
            drive_svc.files().update(
                fileId=doc_id,
                addParents=folder_id,
                removeParents=prev_parents,
                fields="id,parents",
            ).execute()

        return doc_id
    except Exception as e:
        logging.error("Google Docs: create_doc error: %s", e)
        return None


async def create_doc(title: str, content: str, folder_id: str = None,
                     user_id: int = 0, object_type: str = "note",
                     object_id: int = 0) -> Optional[str]:
    """Async: create a Google Doc and return its URL."""
    import asyncio
    loop = asyncio.get_event_loop()
    doc_id = await loop.run_in_executor(
        None, _create_doc_sync, title, content, folder_id
    )
    if not doc_id:
        return None

    url = get_doc_url(doc_id)
    if user_id:
        from bot.db.database import db
        await db.google_link_save(
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            google_type="doc",
            doc_id=doc_id,
            url=url,
        )
    return url


async def make_summary(text: str, max_chars: int = 300) -> str:
    """Generate a short summary of long text using AI."""
    if len(text) <= max_chars:
        return text
    try:
        from openai import AsyncOpenAI
        import config
        from bot.ai.model_router import get_model
        client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=get_model("chat"),
            messages=[
                {"role": "system", "content": "Сделай краткое резюме текста (2-3 предложения, по-русски)."},
                {"role": "user", "content": text[:3000]},
            ],
            max_completion_tokens=150,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.warning("Google Docs: summary generation failed: %s", e)
        return text[:max_chars] + "..."
