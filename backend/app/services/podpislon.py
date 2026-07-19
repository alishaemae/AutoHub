
import base64
import logging
import re
import uuid

import httpx

from ..config import settings

log = logging.getLogger("podpislon")


def is_live() -> bool:
    return bool(settings.podpislon_api_key)


def _headers():
    return {"X-Api-Key": settings.podpislon_api_key}


def _norm_phone(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("8") and len(d) == 11:
        d = "7" + d[1:]
    if len(d) == 10:
        d = "7" + d
    return d


def _split_name(full_name: str):

    parts = [p for p in (full_name or "").split() if p.strip("-—–")]
    if len(parts) >= 3:
        last, name, second = parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        last, name, second = parts[0], parts[1], ""
    elif len(parts) == 1:
        last, name, second = parts[0], parts[0], ""
    else:
        last, name, second = "Клиент", "Клиент", ""
    return name, last, second


async def create_document(pdf_bytes: bytes, signer_name: str, signer_phone: str,
                          title: str) -> dict:
    if not is_live():
        stub_id = "stub-" + uuid.uuid4().hex[:12]
        log.warning("Podpislon в режиме ЗАГЛУШКИ (нет ключа). doc_id=%s", stub_id)
        return {"doc_id": stub_id,
                "sign_url": "https://podpislon.ru/sign/" + stub_id, "stub": True}

    name, last, second = _split_name(signer_name)
    data = {"name": name, "last_name": last, "phone": _norm_phone(signer_phone),
            "agreement": "Y"}
    if second:
        data["second_name"] = second
    files = {"file[]": (f"{title}.pdf", pdf_bytes, "application/pdf")}

    async with httpx.AsyncClient(base_url=settings.podpislon_base_url,
                                 headers=_headers(), timeout=40) as cli:
        r = await cli.put("/add-document", data=data, files=files)
        if r.status_code >= 400:
            log.error("Podpislon /add-document HTTP %s: %s", r.status_code, r.text[:500])
        r.raise_for_status()
        body = r.json()
    log.info("Podpislon /add-document ответ: %s", str(body)[:300])
    if not body.get("status"):
        raise RuntimeError(str(body.get("message") or body))

    result = body.get("result")

    doc_id, sign_url = None, None
    if isinstance(result, dict):
        files_ids = result.get("files") or []
        links = result.get("links") or []
        doc_id = str(files_ids[0]) if files_ids else None
        sign_url = links[0] if links else None
    elif isinstance(result, list):
        doc_id = str(result[0]) if result else None
    elif result is not None:
        doc_id = str(result)
    return {"doc_id": doc_id, "sign_url": sign_url, "stub": False}


async def get_signed_file(doc_id: str) -> bytes | None:
    if not is_live() or str(doc_id).startswith("stub-"):
        return None
    async with httpx.AsyncClient(base_url=settings.podpislon_base_url,
                                 headers=_headers(), timeout=40) as cli:
        r = await cli.post("/get-file", json={"id": int(doc_id)})
        r.raise_for_status()
        body = r.json()
    if body.get("status") and body.get("result"):
        try:
            return base64.b64decode(body["result"])
        except Exception:
            return None
    return None


def parse_webhook(form: dict) -> dict:

    event = (form.get("EVENT") or "").upper()
    doc_id = str(form.get("FILE_ID") or "")
    return {"doc_id": doc_id, "signed": event == "DOCUMENT_SIGNED",
            "event": event, "signature": form.get("SIGNATURE", "")}
