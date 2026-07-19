from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Role, User
from ..schemas import (ClientCreate, PasswordChange, ProfileUpdate, Token,
                       UserOut)
from ..security import (create_access_token, create_reset_token,
                        get_current_user, hash_password, verify_password,
                        verify_reset_token)
from ..services.mailer import send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


@router.post("/register", response_model=Token, status_code=201)
async def register(data: ClientCreate, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where(User.email == data.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Пользователь с такой почтой уже существует")
    user = User(email=data.email, phone=data.phone, full_name=data.full_name,
                role=Role.client, hashed_password=hash_password(data.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return Token(access_token=create_access_token(user.id))


@router.post("/login", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_db)):

    res = await db.execute(select(User).where(User.email == form.username))
    user = res.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Учётная запись отключена")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
async def change_password(data: PasswordChange,
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(data.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Текущий пароль неверен")
    user.hashed_password = hash_password(data.new_password)
    await db.commit()


@router.post("/forgot-password", status_code=200)
async def forgot_password(data: ForgotPasswordIn,
                          db: AsyncSession = Depends(get_db)):

    res = await db.execute(select(User).where(User.email == data.email.lower()))
    user = res.scalar_one_or_none()
    if user and user.is_active:
        token = create_reset_token(user.id)
        base = (settings.public_url or "https://lk.avto-hub.online").rstrip("/")
        link = f"{base}/reset.html?token={token}"
        await send_password_reset_email(user.email, user.full_name or "", link)
    return {"ok": True,
            "message": "Если такой адрес зарегистрирован, на него отправлено письмо."}


@router.post("/reset-password", status_code=200)
async def reset_password(data: ResetPasswordIn,
                         db: AsyncSession = Depends(get_db)):
    user_id = verify_reset_token(data.token)
    if not user_id:
        raise HTTPException(status_code=400,
                            detail="Ссылка недействительна или устарела")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400,
                            detail="Пароль должен быть не короче 6 символов")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    user.hashed_password = hash_password(data.new_password)
    await db.commit()
    return {"ok": True}


@router.patch("/profile", response_model=UserOut)
async def update_profile(data: ProfileUpdate,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.commit()
    await db.refresh(user)
    return user
