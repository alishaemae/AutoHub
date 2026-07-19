
import os
import uuid
from decimal import Decimal

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import (CAR_STATUS_LABELS, Car, CarDocument, CarPhoto,
                     CurrencyCode, CurrencyRate, DocType, Role, StatusHistory,
                     Transaction, TxDirection, User)
from ..schemas import (BalanceOut, CarCreate, CarDocumentOut, CarOut,
                      CarStatusUpdate, CarUpdate, ClientCreate, ClientDetailOut,
                      ClientUpdate, CurrencyOut, CurrencyUpdate, DepositText,
                      PasswordReset, TransactionCreate, TransactionOut,
                      TransactionUpdate, UserOut)
from ..security import hash_password, require_admin
from ..services.mailer import send_status_email

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


async def _build_balance(db: AsyncSession, user_id: int) -> BalanceOut:
    res = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
        .order_by(Transaction.op_date.desc()))
    txs = res.scalars().all()
    inc = [t for t in txs if t.direction == TxDirection.income]
    exp = [t for t in txs if t.direction == TxDirection.expense]
    it = sum((t.amount for t in inc), Decimal(0))
    et = sum((t.amount for t in exp), Decimal(0))
    return BalanceOut(
        balance=it - et, income_total=it, expense_total=et,
        income=[TransactionOut.model_validate(t) for t in inc],
        expense=[TransactionOut.model_validate(t) for t in exp])


async def _serialize_car(db: AsyncSession, car_id: int) -> CarOut:
    res = await db.execute(
        select(Car).options(selectinload(Car.docs), selectinload(Car.photos))
        .where(Car.id == car_id))
    car = res.scalar_one()
    out = CarOut.model_validate(car)
    out.status_label = CAR_STATUS_LABELS.get(car.status, "")
    out.has_photo = bool(car.photo_url)
    out.opis_count = len(car.photos)
    return out


@router.get("/clients/{client_id}", response_model=ClientDetailOut)
async def client_detail(client_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, client_id)
    if not user or user.role != Role.client:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    res = await db.execute(
        select(Car).options(selectinload(Car.docs))
        .where(Car.owner_id == client_id).order_by(Car.purchase_date.desc()))
    cars = []
    for c in res.scalars().all():
        out = CarOut.model_validate(c)
        out.status_label = CAR_STATUS_LABELS.get(c.status, "")
        cars.append(out)
    return ClientDetailOut(
        user=UserOut.model_validate(user), cars=cars,
        balance=await _build_balance(db, client_id))


@router.post("/cars/{car_id}/documents", response_model=CarDocumentOut,
             status_code=201)
async def upload_document(car_id: int, doc_type: DocType = Form(...),
                          file: UploadFile = File(...),
                          db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Допускается только PDF")
    safe = f"{uuid.uuid4().hex}.pdf"
    path = os.path.join(UPLOAD_DIR, safe)
    with open(path, "wb") as f:
        f.write(await file.read())

    res = await db.execute(select(CarDocument).where(
        CarDocument.car_id == car_id, CarDocument.doc_type == doc_type))
    doc = res.scalar_one_or_none()
    if doc:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
        doc.filename, doc.file_path = file.filename, path
    else:
        doc = CarDocument(car_id=car_id, doc_type=doc_type,
                          filename=file.filename, file_path=path)
        db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/clients", response_model=list[UserOut])
async def list_clients(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.role == Role.client))
    return res.scalars().all()


@router.post("/clients", response_model=UserOut, status_code=201)
async def create_client(data: ClientCreate, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where(User.email == data.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Клиент с такой почтой уже есть")
    user = User(email=data.email, phone=data.phone, full_name=data.full_name,
                role=Role.client, hashed_password=hash_password(data.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/clients/{client_id}", response_model=UserOut)
async def edit_client(client_id: int, data: ClientUpdate,
                      db: AsyncSession = Depends(get_db)):
    user = await db.get(User, client_id)
    if not user or user.role != Role.client:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    if data.email and data.email != user.email:
        dup = await db.execute(select(User).where(User.email == data.email))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Почта уже занята")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/clients/{client_id}/password", status_code=204)
async def reset_client_password(client_id: int, data: PasswordReset,
                                db: AsyncSession = Depends(get_db)):
    user = await db.get(User, client_id)
    if not user or user.role != Role.client:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    user.hashed_password = hash_password(data.password)
    await db.commit()


@router.delete("/clients/{client_id}", status_code=204)
async def delete_client(client_id: int, db: AsyncSession = Depends(get_db)):

    user = await db.get(User, client_id)
    if not user or user.role != Role.client:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    from ..models import Car, CarPhoto, DepositReceipt, SignableDocument
    paths: list[str] = []
    cars = (await db.execute(
        select(Car).options(selectinload(Car.docs), selectinload(Car.photos))
        .where(Car.owner_id == client_id))).scalars().all()
    for car in cars:
        if car.photo_url:
            paths.append(car.photo_url)
        for d in car.docs:
            paths.append(d.file_path)
            if d.receipt_path:
                paths.append(d.receipt_path)
        paths += [p.file_path for p in car.photos]
    sdocs = (await db.execute(
        select(SignableDocument).where(SignableDocument.user_id == client_id))).scalars().all()
    for sd in sdocs:
        for pth in (sd.pdf_path, sd.passport_main_path, sd.passport_reg_path):
            if pth:
                paths.append(pth)

    dep_receipts = (await db.execute(
        select(DepositReceipt).where(DepositReceipt.user_id == client_id))).scalars().all()
    for dr in dep_receipts:
        if dr.file_path:
            paths.append(dr.file_path)
        await db.delete(dr)
    await db.delete(user)
    await db.commit()

    for pth in paths:
        try:
            if pth and os.path.exists(pth):
                os.remove(pth)
        except OSError:
            pass


@router.post("/cars/{car_id}/photo", response_model=CarOut)
async def upload_car_photo(car_id: int, file: UploadFile = File(...),
                           db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="Допускается изображение (jpg/png/webp)")
    path = os.path.join(UPLOAD_DIR, f"car{car_id}_photo{ext}")
    with open(path, "wb") as f:
        f.write(await file.read())
    car.photo_url = path
    await db.commit()
    return await _serialize_car(db, car_id)


@router.post("/cars/{car_id}/opis", response_model=CarOut)
async def upload_car_opis(car_id: int, files: list[UploadFile] = File(...),
                          db: AsyncSession = Depends(get_db)):
    """Добавить фотографии в фотоопись (можно несколько за раз)."""
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    added = 0
    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        content = await file.read()

        import uuid as _uuid
        path = os.path.join(UPLOAD_DIR, f"car{car_id}_opis_{_uuid.uuid4().hex[:8]}{ext}")
        with open(path, "wb") as f:
            f.write(content)
        db.add(CarPhoto(car_id=car_id, file_path=path))
        added += 1
    if added == 0:
        raise HTTPException(status_code=400,
                            detail="Загрузите изображения (jpg, png, webp)")
    await db.commit()
    return await _serialize_car(db, car_id)


@router.post("/cars/{car_id}/opis/zip", response_model=CarOut)
async def upload_car_opis_zip(car_id: int, file: UploadFile = File(...),
                              db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    content = await file.read()
    if not content.startswith(b"PK\x03\x04") and not content.startswith(b"PK\x05\x06"):
        raise HTTPException(status_code=400, detail="Это не ZIP-архив")
    import io
    import uuid as _uuid
    import zipfile
    added = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            for name in z.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                data = z.read(name)
                path = os.path.join(UPLOAD_DIR, f"car{car_id}_opis_{_uuid.uuid4().hex[:8]}{ext}")
                with open(path, "wb") as f:
                    f.write(data)
                db.add(CarPhoto(car_id=car_id, file_path=path))
                added += 1
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Повреждённый ZIP-архив")
    if added == 0:
        raise HTTPException(status_code=400,
                            detail="В архиве нет изображений (jpg, png, webp)")
    await db.commit()
    return await _serialize_car(db, car_id)


@router.delete("/cars/{car_id}/documents/{doc_id}", response_model=CarOut)
async def delete_car_document(car_id: int, doc_id: int,
                              db: AsyncSession = Depends(get_db)):
    doc = await db.get(CarDocument, doc_id)
    if not doc or doc.car_id != car_id:
        raise HTTPException(status_code=404, detail="Документ не найден")
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass
    await db.delete(doc)
    await db.commit()
    return await _serialize_car(db, car_id)


@router.delete("/cars/{car_id}/photo", response_model=CarOut)
async def delete_car_photo(car_id: int, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    try:
        if car.photo_url and os.path.exists(car.photo_url):
            os.remove(car.photo_url)
    except OSError:
        pass
    car.photo_url = ""
    await db.commit()
    return await _serialize_car(db, car_id)


@router.delete("/cars/{car_id}/opis/{photo_id}", response_model=CarOut)
async def delete_car_opis(car_id: int, photo_id: int,
                          db: AsyncSession = Depends(get_db)):
    photo = await db.get(CarPhoto, photo_id)
    if not photo or photo.car_id != car_id:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    try:
        if os.path.exists(photo.file_path):
            os.remove(photo.file_path)
    except OSError:
        pass
    await db.delete(photo)
    await db.commit()
    return await _serialize_car(db, car_id)


@router.post("/cars", response_model=CarOut, status_code=201)
async def create_car(data: CarCreate, db: AsyncSession = Depends(get_db)):
    owner = await db.get(User, data.owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    car = Car(**data.model_dump())
    db.add(car)
    await db.commit()
    await db.refresh(car)
    return await _serialize_car(db, car.id)


@router.patch("/cars/{car_id}", response_model=CarOut)
async def edit_car(car_id: int, data: CarUpdate,
                   db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(car, field, val)
    await db.commit()
    return await _serialize_car(db, car_id)


@router.delete("/cars/{car_id}", status_code=204)
async def delete_car(car_id: int, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    await db.delete(car)
    await db.commit()


@router.patch("/cars/{car_id}/status", response_model=CarOut)
async def update_status(car_id: int, data: CarStatusUpdate,
                        db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    old = car.status
    car.status = data.status

    hist = StatusHistory(car_id=car.id, old_status=old.value,
                         new_status=data.status.value)
    db.add(hist)
    await db.commit()
    await db.refresh(car)


    owner = await db.get(User, car.owner_id)
    sent = None
    if owner:
        sent = await send_status_email(
            to_email=owner.email, full_name=owner.full_name,
            car_label=car.make_model, status_value=car.status.value,
            status_label=CAR_STATUS_LABELS.get(car.status, ""))
        if sent:
            hist.email_sent = True
            await db.commit()

    out = await _serialize_car(db, car.id)
    out.email_sent = sent
    return out


@router.post("/transactions", response_model=TransactionOut, status_code=201)
async def add_transaction(data: TransactionCreate,
                          db: AsyncSession = Depends(get_db)):
    if not await db.get(User, data.user_id):
        raise HTTPException(status_code=404, detail="Клиент не найден")
    tx = Transaction(**data.model_dump())
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
async def edit_transaction(tx_id: int, data: TransactionUpdate,
                           db: AsyncSession = Depends(get_db)):
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(tx, field, val)
    await db.commit()
    await db.refresh(tx)
    return tx


@router.delete("/transactions/{tx_id}", status_code=204)
async def delete_transaction(tx_id: int, db: AsyncSession = Depends(get_db)):
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    await db.delete(tx)
    await db.commit()


@router.put("/currency/{code}", response_model=CurrencyOut)
async def update_currency(code: CurrencyCode, data: CurrencyUpdate,
                          db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(CurrencyRate).where(CurrencyRate.code == code))
    rate = res.scalar_one_or_none()
    if not rate:
        rate = CurrencyRate(code=code, rate=data.rate)
        db.add(rate)
    else:
        rate.rate = data.rate
    await db.commit()
    await db.refresh(rate)
    return rate


@router.get("/deposit")
async def admin_get_deposit(db: AsyncSession = Depends(get_db)):
    from ..models import Setting
    row = await db.get(Setting, "deposit_text")
    def _has(base):
        p = os.path.join(UPLOAD_DIR, base)
        return any(os.path.exists(p + ext) for ext in (".png", ".jpg", ".jpeg"))
    return {"text": row.value if row else "",
            "has_qr": _has("deposit_qr"),
            "has_qr_tbank": _has("deposit_qr_tbank")}


@router.get("/clients/{user_id}/deposit-receipts")
async def client_deposit_receipts(user_id: int, db: AsyncSession = Depends(get_db)):
    from ..models import DepositReceipt
    res = await db.execute(select(DepositReceipt)
                           .where(DepositReceipt.user_id == user_id)
                           .order_by(DepositReceipt.uploaded_at.desc()))
    return [{"id": r.id, "filename": r.filename,
             "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else ""}
            for r in res.scalars().all()]


_DOC_RECEIPT_LABEL = {"car_payment": "Оплата за авто", "customs": "Таможня",
                      "broker": "Брокер"}


async def _receipt_events(db: AsyncSession):
    from ..models import DepositReceipt
    events = []
    dres = await db.execute(
        select(DepositReceipt, User)
        .join(User, DepositReceipt.user_id == User.id)
        .order_by(DepositReceipt.uploaded_at.desc()))
    for r, u in dres.all():
        events.append({"client_id": u.id, "client_name": u.full_name or u.email,
                       "label": "Депозит", "car": "",
                       "at": r.uploaded_at, "url": f"/api/deposit/receipts/{r.id}"})
    cres = await db.execute(
        select(CarDocument, Car, User)
        .join(Car, CarDocument.car_id == Car.id)
        .join(User, Car.owner_id == User.id)
        .where(CarDocument.receipt_path != ""))
    for doc, car, u in cres.all():
        events.append({"client_id": u.id, "client_name": u.full_name or u.email,
                       "label": _DOC_RECEIPT_LABEL.get(doc.doc_type.value, "Оплата"),
                       "car": car.make_model,
                       "at": doc.receipt_uploaded_at or doc.uploaded_at,
                       "url": f"/api/car-documents/{doc.id}/receipt"})
    events.sort(key=lambda e: e["at"] or 0, reverse=True)
    return events


def _parse_dt(v):
    from datetime import datetime
    if not v:
        return None
    try:
        s = str(v).replace("T", " ").replace("Z", "")
        if "+" in s:
            s = s.split("+")[0]
        s = s.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    except Exception:
        return None
    return None


def _to_naive(dt):
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


@router.get("/notifications")
async def notifications(db: AsyncSession = Depends(get_db)):
    from ..models import Setting
    seen_row = await db.get(Setting, "notifications_seen_at")
    cleared_row = await db.get(Setting, "notifications_cleared_at")
    seen_dt = _parse_dt(seen_row.value if seen_row else "")
    cleared_dt = _parse_dt(cleared_row.value if cleared_row else "")
    events = await _receipt_events(db)
    items, unseen = [], 0
    for e in events[:80]:
        edt = _to_naive(e["at"])
        at_iso = e["at"].isoformat() if e["at"] else ""
        if cleared_dt and edt and edt <= cleared_dt:
            continue
        is_new = bool(edt) and (not seen_dt or edt > seen_dt)
        if is_new:
            unseen += 1
        items.append({"client_id": e["client_id"], "client_name": e["client_name"],
                      "label": e["label"], "car": e["car"],
                      "uploaded_at": at_iso, "new": is_new})
    return {"unseen": unseen, "items": items}


@router.post("/notifications/seen", status_code=204)
async def notifications_seen(db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    from ..models import Setting
    row = await db.get(Setting, "notifications_seen_at")
    now = datetime.now(timezone.utc).isoformat()
    if row:
        row.value = now
    else:
        db.add(Setting(key="notifications_seen_at", value=now))
    await db.commit()


@router.post("/notifications/clear", status_code=204)
async def notifications_clear(db: AsyncSession = Depends(get_db)):
    """Очистить поле уведомлений — скрыть все текущие до этого момента."""
    from datetime import datetime, timezone
    from ..models import Setting
    now = datetime.now(timezone.utc).isoformat()
    for key in ("notifications_cleared_at", "notifications_seen_at"):
        row = await db.get(Setting, key)
        if row:
            row.value = now
        else:
            db.add(Setting(key=key, value=now))
    await db.commit()


@router.get("/clients/{user_id}/receipts")
async def client_all_receipts(user_id: int, db: AsyncSession = Depends(get_db)):
    from ..models import DepositReceipt
    out = []
    dres = await db.execute(select(DepositReceipt)
                            .where(DepositReceipt.user_id == user_id)
                            .order_by(DepositReceipt.uploaded_at.desc()))
    for r in dres.scalars().all():
        out.append({"kind": "deposit", "label": "Депозит", "car": "",
                    "filename": r.filename,
                    "url": f"/api/deposit/receipts/{r.id}",
                    "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else ""})
    cres = await db.execute(
        select(CarDocument, Car)
        .join(Car, CarDocument.car_id == Car.id)
        .where(Car.owner_id == user_id, CarDocument.receipt_path != "")
        .order_by(CarDocument.uploaded_at.desc()))
    for doc, car in cres.all():
        out.append({"kind": doc.doc_type.value,
                    "label": _DOC_RECEIPT_LABEL.get(doc.doc_type.value, "Оплата"),
                    "car": car.make_model,
                    "filename": doc.receipt_name or "чек",
                    "url": f"/api/car-documents/{doc.id}/receipt",
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else ""})
    return out


@router.put("/deposit", status_code=204)
async def set_deposit_text(data: DepositText, db: AsyncSession = Depends(get_db)):
    from ..models import Setting
    row = await db.get(Setting, "deposit_text")
    if row:
        row.value = data.text
    else:
        db.add(Setting(key="deposit_text", value=data.text))
    await db.commit()


@router.post("/deposit/qr", status_code=204)
async def upload_deposit_qr(bank: str = "sber", file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=400, detail="Загрузите изображение QR (png или jpg)")
    base = "deposit_qr" if bank == "sber" else "deposit_qr_" + bank
    for old in (".png", ".jpg", ".jpeg"):
        p = os.path.join(UPLOAD_DIR, base + old)
        if os.path.exists(p):
            os.remove(p)
    with open(os.path.join(UPLOAD_DIR, base + ext), "wb") as f:
        f.write(await file.read())


@router.delete("/deposit/qr", status_code=204)
async def delete_deposit_qr(bank: str = "sber"):
    base = "deposit_qr" if bank == "sber" else "deposit_qr_" + bank
    for ext in (".png", ".jpg", ".jpeg"):
        p = os.path.join(UPLOAD_DIR, base + ext)
        if os.path.exists(p):
            os.remove(p)
