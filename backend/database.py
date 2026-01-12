import aiosqlite
import json
from datetime import datetime
from typing import List, Optional
from .models import InvoiceData


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = "data/invoices.db"):
        self.db_path = db_path

    async def init_db(self):
        """初始化数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    invoice_number TEXT NOT NULL,
                    invoice_date TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    qr_code_data TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            await db.commit()

    async def save_invoice(self, invoice: InvoiceData) -> bool:
        """保存发票数据"""
        if not invoice.id:
            invoice.id = f"{invoice.invoice_number}_{invoice.invoice_date}"

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO invoices
                    (id, invoice_number, invoice_date, total_amount, qr_code_data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    invoice.id,
                    invoice.invoice_number,
                    invoice.invoice_date,
                    invoice.total_amount,
                    invoice.qr_code_data,
                    invoice.created_at.isoformat()
                ))
                await db.commit()
                return True
        except Exception as e:
            print(f"保存失败: {e}")
            return False

    async def get_all_invoices(self) -> List[InvoiceData]:
        """获取所有发票"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM invoices ORDER BY created_at DESC")
            rows = await cursor.fetchall()

            return [
                InvoiceData(
                    id=row["id"],
                    invoice_number=row["invoice_number"],
                    invoice_date=row["invoice_date"],
                    total_amount=row["total_amount"],
                    qr_code_data=row["qr_code_data"],
                    created_at=datetime.fromisoformat(row["created_at"])
                )
                for row in rows
            ]

    async def delete_invoice(self, invoice_id: str) -> bool:
        """删除发票"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"删除失败: {e}")
            return False

    async def clear_all(self) -> bool:
        """清空所有发票"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM invoices")
                await db.commit()
                return True
        except Exception as e:
            print(f"清空失败: {e}")
            return False


# 全局数据库实例
db = Database()
