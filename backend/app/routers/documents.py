import json
import os
from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import (Role, SignableDocument, SignableKind, SignStatus, User)
from ..schemas import SignableOut
from ..security import get_current_user
from ..services import podpislon
from ..services.pdf_gen import generate_signable_pdf

router = APIRouter(prefix="/api", tags=["documents"])
SIGN_DIR = "uploads/signable"
PASS_DIR = "uploads/passport"


def _to_out(doc: SignableDocument) -> SignableOut:
    o = SignableOut.model_validate(doc)
    o.has_pdf = bool(doc.pdf_path and os.path.exists(doc.pdf_path))
    o.has_passport = bool(doc.passport_main_path or doc.passport_reg_path)
    return o


async def _latest_contract(db: AsyncSession, user_id: int):
    res = await db.execute(
        select(SignableDocument)
        .where(SignableDocument.user_id == user_id,
               SignableDocument.kind == SignableKind.contract)
        .order_by(SignableDocument.created_at.desc()))
    return res.scalars().first()


@router.post("/documents/sign")
async def create_and_send(
        kind: SignableKind = Form(...),
        form_data: str = Form("{}"),
        passport_main: UploadFile | None = File(None),
        passport_reg: UploadFile | None = File(None),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):

    data = json.loads(form_data or "{}")


    if kind == SignableKind.return_request:
        c = await _latest_contract(db, user.id)
        if c:
            cd = json.loads(c.form_data or "{}")
            data.setdefault("fio", cd.get("fio", ""))
            data.setdefault("passport_series", cd.get("passport_series", ""))
            data.setdefault("passport_number", cd.get("passport_number", ""))
            data.setdefault("passport_issued", cd.get("passport_issued", ""))
            data.setdefault("address", cd.get("address", ""))
            data.setdefault("contract_number", c.doc_number or f"АХ-{c.id:05d}")
            data.setdefault("contract_date", c.doc_date or "")

    from datetime import date
    doc = SignableDocument(user_id=user.id, kind=kind, status=SignStatus.draft,
                           form_data=json.dumps(data, ensure_ascii=False))
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    doc.doc_number = f"АХ-{doc.id:05d}"
    doc.doc_date = f"{date.today():%d.%m.%Y} г."


    if passport_main and passport_main.filename:
        os.makedirs(PASS_DIR, exist_ok=True)
        ext = os.path.splitext(passport_main.filename)[1].lower() or ".jpg"
        p = os.path.join(PASS_DIR, f"{doc.id}_main{ext}")
        with open(p, "wb") as f:
            f.write(await passport_main.read())
        doc.passport_main_path = p
    if passport_reg and passport_reg.filename:
        os.makedirs(PASS_DIR, exist_ok=True)
        ext = os.path.splitext(passport_reg.filename)[1].lower() or ".jpg"
        p = os.path.join(PASS_DIR, f"{doc.id}_reg{ext}")
        with open(p, "wb") as f:
            f.write(await passport_reg.read())
        doc.passport_reg_path = p

    pdf_path = os.path.join(SIGN_DIR, f"{doc.id}.pdf")
    data["phone"] = user.phone or ""
    generate_signable_pdf(kind.value, data, pdf_path,
                          doc_number=doc.doc_number, doc_date=doc.doc_date)
    doc.pdf_path = pdf_path

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    title = "Договор" if kind == SignableKind.contract else "Заявление о возврате"
    try:
        res = await podpislon.create_document(
            pdf_bytes, signer_name=user.full_name or user.email,
            signer_phone=user.phone, title=title)
    except Exception as e:
        import logging
        logging.getLogger("podpislon").exception(
            "Ошибка при отправке в Podpislon (телефон=%s)", user.phone)
        raise HTTPException(
            status_code=502,
            detail=f"Podpislon: не удалось отправить документ ({type(e).__name__}: {e})")
    doc.podpislon_doc_id = res["doc_id"] or ""
    doc.status = SignStatus.sent
    await db.commit()
    await db.refresh(doc)
    return {"id": doc.id, "status": doc.status.value,
            "sign_url": res.get("sign_url"), "stub": res.get("stub", False)}


@router.get("/documents/mine", response_model=list[SignableOut])
async def my_documents(user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(SignableDocument).where(SignableDocument.user_id == user.id)
        .order_by(SignableDocument.created_at.desc()))
    return [_to_out(d) for d in res.scalars().all()]


@router.post("/documents/{doc_id}/refresh")
async def refresh_document(doc_id: int, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):

    doc = await db.get(SignableDocument, doc_id)
    if not doc or (user.role != Role.admin and doc.user_id != user.id):
        raise HTTPException(status_code=404, detail="Документ не найден")
    if doc.status == SignStatus.signed:
        return {"status": "signed", "updated": False}
    if not doc.podpislon_doc_id or doc.podpislon_doc_id.startswith("stub-"):
        return {"status": doc.status.value, "updated": False, "stub": True}
    return {"status": doc.status.value, "updated": False}


@router.get("/documents/{doc_id}/file")
async def document_file(doc_id: int, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    doc = await db.get(SignableDocument, doc_id)
    if not doc or (user.role != Role.admin and doc.user_id != user.id):
        raise HTTPException(status_code=404, detail="Документ не найден")
    if not doc.pdf_path or not os.path.exists(doc.pdf_path):
        raise HTTPException(status_code=404, detail="Файл отсутствует")
    return FileResponse(doc.pdf_path, media_type="application/pdf",
                        filename=f"document-{doc.id}.pdf")


@router.get("/documents/{doc_id}/passport/{which}")
async def document_passport(doc_id: int, which: str,
                            user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    doc = await db.get(SignableDocument, doc_id)
    if not doc or (user.role != Role.admin and doc.user_id != user.id):
        raise HTTPException(status_code=404, detail="Документ не найден")
    path = doc.passport_main_path if which == "main" else doc.passport_reg_path
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл отсутствует")
    return FileResponse(path)


@router.post("/webhooks/podpislon")
async def podpislon_webhook(request: Request, db: AsyncSession = Depends(get_db)):

    form = dict(await request.form())
    info = podpislon.parse_webhook(form)
    if not info["doc_id"]:
        return {"ok": False, "reason": "no file id"}
    res = await db.execute(select(SignableDocument)
                           .where(SignableDocument.podpislon_doc_id == info["doc_id"]))
    doc = res.scalar_one_or_none()
    if not doc:
        return {"ok": False, "reason": "doc not found"}
    if info["signed"]:
        doc.status = SignStatus.signed
        doc.signed_at = datetime.now(timezone.utc)
        signed = await podpislon.get_signed_file(info["doc_id"])
        if signed:
            with open(doc.pdf_path, "wb") as f:
                f.write(signed)
        await db.commit()
    return {"ok": True, "status": doc.status.value}
