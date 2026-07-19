from datetime import date
from decimal import Decimal

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import (Car, CarStatus, CurrencyCode, CurrencyRate, Role,
                     Transaction, TxDirection, User)
from .security import hash_password


async def seed():
    async with SessionLocal() as db:
        if (await db.execute(select(User).limit(1))).scalar_one_or_none():
            return

        admin = User(email=settings.admin_email, phone="+7 999 000-00-00",
                     full_name="Менеджер AVTO-hub", role=Role.admin,
                     hashed_password=hash_password(settings.admin_password))
        db.add(admin)

        db.add_all([
            CurrencyRate(code=CurrencyCode.JPY, rate=Decimal("48.35")),
            CurrencyRate(code=CurrencyCode.EUR, rate=Decimal("84.67")),
        ])

        if settings.auto_create_tables:
            await db.flush()
            demo = User(email="client@avto-hub.ru", phone="+7 905 123-45-21",
                        full_name="Дмитрий Соколов", role=Role.client,
                        hashed_password=hash_password("client123"))
            db.add(demo)
            await db.flush()
            db.add_all([
                Car(owner_id=demo.id, make_model="Toyota Land Cruiser 300",
                    year=2023, body_number="VJA300W-0148820",
                    purchase_date=date(2024, 1, 18),
                    status=CarStatus.ship_assigned, ship_name="Grand Mercury"),
                Car(owner_id=demo.id, make_model="Lexus RX 350", year=2022,
                    body_number="TALA15-1009934", purchase_date=date(2024, 2, 2),
                    status=CarStatus.customs_invoice, ship_name="Sun Rio"),
                Car(owner_id=demo.id, make_model="Toyota Alphard", year=2024,
                    body_number="AGH40W-0021507", purchase_date=date(2024, 2, 25),
                    status=CarStatus.purchased),
            ])
            db.add_all([
                Transaction(user_id=demo.id, op_date=date(2024, 1, 15),
                            name="Пополнение депозита", payer="Соколов Д. А.",
                            amount=Decimal("5000000"), direction=TxDirection.income),
                Transaction(user_id=demo.id, op_date=date(2024, 2, 2),
                            name="Пополнение депозита", payer="Соколов Д. А.",
                            amount=Decimal("3000000"), direction=TxDirection.income),
                Transaction(user_id=demo.id, op_date=date(2024, 1, 20),
                            name="Оплата авто · Land Cruiser 300", payer="AVTO-hub",
                            amount=Decimal("4800000"), direction=TxDirection.expense),
                Transaction(user_id=demo.id, op_date=date(2024, 2, 8),
                            name="Таможенные платежи · Land Cruiser", payer="AVTO-hub",
                            amount=Decimal("1100000"), direction=TxDirection.expense),
            ])

        await db.commit()
