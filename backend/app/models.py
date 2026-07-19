from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (DateTime, Enum, ForeignKey, Numeric, String, Text,
                        func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Role(str, enum.Enum):
    client = "client"
    admin = "admin"


class CarStatus(str, enum.Enum):
    purchased = "purchased"
    invoice_jp = "invoice_jp"
    to_port = "to_port"
    ship_assigned = "ship_assigned"
    customs_invoice = "customs_invoice"
    released = "released"


CAR_STATUS_LABELS = {
    CarStatus.purchased: "Куплен автомобиль",
    CarStatus.invoice_jp: "Выставлен счёт по Японии",
    CarStatus.to_port: "Доставка в порт",
    CarStatus.ship_assigned: "Назначение судна",
    CarStatus.customs_invoice: "Выставлен счёт за таможенную очистку",
    CarStatus.released: "Растаможен и готов к выдаче",
}


class DocType(str, enum.Enum):
    car_payment = "car_payment"
    customs = "customs"
    broker = "broker"


class TxDirection(str, enum.Enum):
    income = "income"
    expense = "expense"


class SignableKind(str, enum.Enum):
    contract = "contract"
    return_request = "return_request"


class SignStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    signed = "signed"


class CurrencyCode(str, enum.Enum):
    JPY = "JPY"
    EUR = "EUR"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(32), default="")
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.client)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    cars: Mapped[list["Car"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    documents: Mapped[list["SignableDocument"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    make_model: Mapped[str] = mapped_column(String(255))
    year: Mapped[int] = mapped_column()
    body_number: Mapped[str] = mapped_column(String(64))
    purchase_date: Mapped[date] = mapped_column()
    status: Mapped[CarStatus] = mapped_column(
        Enum(CarStatus), default=CarStatus.purchased)
    ship_name: Mapped[str] = mapped_column(String(128), default="")
    ship_arrival_date: Mapped[str] = mapped_column(String(32), default="")
    photo_url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner: Mapped["User"] = relationship(back_populates="cars")
    docs: Mapped[list["CarDocument"]] = relationship(
        back_populates="car", cascade="all, delete-orphan")
    photos: Mapped[list["CarPhoto"]] = relationship(
        back_populates="car", cascade="all, delete-orphan",
        order_by="CarPhoto.id")
    history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="car", cascade="all, delete-orphan")


class CarDocument(Base):
    __tablename__ = "car_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType))
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    receipt_path: Mapped[str] = mapped_column(String(512), default="")
    receipt_name: Mapped[str] = mapped_column(String(255), default="")
    receipt_uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    car: Mapped["Car"] = relationship(back_populates="docs")

    @property
    def has_receipt(self) -> bool:
        return bool(self.receipt_path)


class CarPhoto(Base):
    __tablename__ = "car_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    car: Mapped["Car"] = relationship(back_populates="photos")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    old_status: Mapped[str] = mapped_column(String(32), default="")
    new_status: Mapped[str] = mapped_column(String(32))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    email_sent: Mapped[bool] = mapped_column(default=False)

    car: Mapped["Car"] = relationship(back_populates="history")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    op_date: Mapped[date] = mapped_column()
    name: Mapped[str] = mapped_column(String(255))
    payer: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    direction: Mapped[TxDirection] = mapped_column(Enum(TxDirection))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")


class SignableDocument(Base):
    __tablename__ = "signable_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[SignableKind] = mapped_column(Enum(SignableKind))
    status: Mapped[SignStatus] = mapped_column(
        Enum(SignStatus), default=SignStatus.draft)
    form_data: Mapped[str] = mapped_column(Text, default="{}")
    doc_number: Mapped[str] = mapped_column(String(32), default="")
    doc_date: Mapped[str] = mapped_column(String(32), default="")
    pdf_path: Mapped[str] = mapped_column(String(512), default="")
    passport_main_path: Mapped[str] = mapped_column(String(512), default="")
    passport_reg_path: Mapped[str] = mapped_column(String(512), default="")
    podpislon_doc_id: Mapped[str] = mapped_column(String(128), default="")
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="documents")


class CurrencyRate(Base):
    __tablename__ = "currency_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[CurrencyCode] = mapped_column(Enum(CurrencyCode), unique=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class DepositReceipt(Base):
    __tablename__ = "deposit_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())
