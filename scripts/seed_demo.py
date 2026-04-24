"""
Demo seed — populate data/ with a handful of fabricated incomes so Diana
can click through every page on day 1 before entering real data.

Usage:
    python scripts/seed_demo.py             # inserts into default DB
    DIANA_TAX_DB=sqlite:///demo.db python scripts/seed_demo.py

Running twice is idempotent: it wipes before inserting so pages don't
fill up with duplicates. Diana's real workflow never touches this script.
"""

import sys
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import delete
from storage.db import init_db, get_session
from core.models import Client, Project, Income, WithholdingSlip, UserSettings


def seed():
    init_db()
    today = date.today()

    with get_session() as s:
        # clean slate
        for m in (Income, WithholdingSlip, Project, Client):
            s.exec(delete(m))
        s.commit()

        # Settings — set occupation to author so expense rate applies correctly
        settings = s.get(UserSettings, 1)
        if settings is None:
            settings = UserSettings(id=1)
        settings.name = "Diana (demo)"
        settings.is_married = False
        settings.dependents = 0
        settings.occupation = "author"
        settings.nhi_insurance_type = "union"
        s.add(settings)

        # Clients
        c1 = Client(name="ABC 出版社", tax_id="12345678", contact_email="editor@abc.tw")
        c2 = Client(name="國立某大學 推廣教育", tax_id="03734901", contact_email="training@ntu.edu.tw")
        c3 = Client(name="XYZ Marketing 行銷", tax_id="23456789", contact_email="ops@xyz.tw")
        c4 = Client(name="海外客戶 Acme Inc", tax_id=None, contact_email="pm@acme.com")
        s.add_all([c1, c2, c3, c4])
        s.flush()

        # Projects (optional, not all incomes need one)
        p_book = Project(client_id=c1.id, name="2026 攝影散文書", default_income_type="9B_author")
        p_workshop = Project(client_id=c2.id, name="攝影工作坊系列", default_income_type="50")
        s.add_all([p_book, p_workshop])
        s.flush()

        # Incomes
        incomes = [
            # 本月剛收
            Income(
                client_id=c1.id, project_id=p_book.id,
                date=today - timedelta(days=5),
                amount=Decimal(50_000), income_type="9B_author",
                tax_withheld=Decimal(5_000), nhi_withheld=Decimal(1_055),
                status="received", received_date=today - timedelta(days=3),
                notes="第一次版稅分潤",
            ),
            # 3 個月前 9B 講演
            Income(
                client_id=c2.id,
                date=today - timedelta(days=90),
                amount=Decimal(30_000), income_type="9B_speech",
                tax_withheld=Decimal(3_000), nhi_withheld=Decimal(633),
                status="received", received_date=today - timedelta(days=85),
            ),
            # 50 授課（兼職薪資、訓練班 → 50）
            Income(
                client_id=c2.id, project_id=p_workshop.id,
                date=today - timedelta(days=40),
                amount=Decimal(40_000), income_type="50",
                tax_withheld=Decimal(0), nhi_withheld=Decimal(844),
                status="received", received_date=today - timedelta(days=30),
            ),
            # 40 天前開的票，還沒收 → 軟逾期
            Income(
                client_id=c3.id,
                date=today - timedelta(days=40),
                amount=Decimal(80_000), income_type="9A",
                tax_withheld=Decimal(0), nhi_withheld=Decimal(0),
                status="invoiced",
                notes="行銷顧問費，本期款",
            ),
            # 80 天前開的票，還沒收 → 硬逾期
            Income(
                client_id=c3.id,
                date=today - timedelta(days=80),
                amount=Decimal(60_000), income_type="9A",
                tax_withheld=Decimal(0), nhi_withheld=Decimal(0),
                status="invoiced",
                notes="上期款，已兩次 email 對方",
            ),
            # 海外
            Income(
                client_id=c4.id,
                date=today - timedelta(days=20),
                amount=Decimal(30_000), income_type="overseas",
                currency="TWD",  # 此處已經折算
                status="received", received_date=today - timedelta(days=20),
                notes="USD 1000 @ 30，Wise 轉入",
            ),
        ]
        s.add_all(incomes)

        # Withholding slips
        slips = [
            WithholdingSlip(
                tax_year=114, payer_name="ABC 出版社", payer_tax_id="12345678",
                income_type="9B_author", gross_amount=Decimal(50_000),
                tax_withheld=Decimal(5_000), nhi_withheld=Decimal(1_055),
            ),
            WithholdingSlip(
                tax_year=114, payer_name="國立某大學 推廣教育", payer_tax_id="03734901",
                income_type="9B_speech", gross_amount=Decimal(30_000),
                tax_withheld=Decimal(3_000), nhi_withheld=Decimal(633),
            ),
            WithholdingSlip(
                tax_year=114, payer_name="國立某大學 推廣教育", payer_tax_id="03734901",
                income_type="50", gross_amount=Decimal(40_000),
                tax_withheld=Decimal(0), nhi_withheld=Decimal(844),
            ),
        ]
        s.add_all(slips)

        s.commit()

    print(f"Seeded: 4 clients, 2 projects, {len(incomes)} incomes, {len(slips)} slips")
    print("Open the app (streamlit run ui/app.py) to poke around.")


if __name__ == "__main__":
    seed()
