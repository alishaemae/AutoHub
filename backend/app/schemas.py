from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from .models import (CarStatus, CurrencyCode, DocType, Role, SignableKind,
                     SignStatus, TxDirection)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    phone: str
    full_name: str
    role: Role


class ClientCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) < 10:
            raise ValueError("Укажите корректный телефон (он нужен для подписи по SMS)")
        return v

    @field_validator("password")
    @classmethod
    def pass_len(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Пароль должен быть не короче 6 символов")
        return v


class ClientUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class PasswordReset(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def pass_len(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Пароль должен быть не короче 6 символов")
        return v


class PasswordChange(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pass_len(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Новый пароль должен быть не короче 6 символов")
        return v


class ProfileUpdate(BaseModel):
    phone: str | None = None
    full_name: str | None = None


class CarDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_type: DocType
    filename: str
    uploaded_at: datetime
    has_receipt: bool = False
    receipt_name: str = ""


class CarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    make_model: str
    year: int
    body_number: str
    purchase_date: date
    status: CarStatus
    status_label: str = ""
    ship_name: str
    ship_arrival_date: str = ""
    photo_url: str
    has_photo: bool = False
    opis_count: int = 0
    docs: list[CarDocumentOut] = []
    email_sent: bool | None = None


class CarCreate(BaseModel):
    owner_id: int
    make_model: str
    year: int
    body_number: str
    purchase_date: date
    ship_name: str = ""
    status: CarStatus = CarStatus.purchased


class CarStatusUpdate(BaseModel):
    status: CarStatus


class CarUpdate(BaseModel):
    make_model: str | None = None
    year: int | None = None
    body_number: str | None = None
    purchase_date: date | None = None
    ship_name: str | None = None
    ship_arrival_date: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    op_date: date
    name: str
    payer: str
    amount: Decimal
    direction: TxDirection


class TransactionCreate(BaseModel):
    user_id: int
    op_date: date
    name: str
    payer: str = ""
    amount: Decimal
    direction: TxDirection


class TransactionUpdate(BaseModel):
    op_date: date | None = None
    name: str | None = None
    payer: str | None = None
    amount: Decimal | None = None
    direction: TxDirection | None = None


class BalanceOut(BaseModel):
    balance: Decimal
    income_total: Decimal
    expense_total: Decimal
    income: list[TransactionOut]
    expense: list[TransactionOut]


class CurrencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: CurrencyCode
    rate: Decimal
    updated_at: datetime


class CurrencyUpdate(BaseModel):
    rate: Decimal


class DepositText(BaseModel):
    text: str


class ClientDetailOut(BaseModel):
    user: UserOut
    cars: list[CarOut]
    balance: BalanceOut


class SignableCreate(BaseModel):
    kind: SignableKind
    form_data: dict = {}


class SignableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: SignableKind
    status: SignStatus
    signed_at: datetime | None = None
    created_at: datetime
    has_pdf: bool = False
    has_passport: bool = False
