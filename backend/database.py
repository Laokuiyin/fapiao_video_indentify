import aiosqlite
import json
from datetime import datetime
from typing import List, Optional
from .models import InvoiceData, Department, Employee, ExpenseReport


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = "data/invoices.db"):
        self.db_path = db_path

    async def init_db(self):
        """初始化数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            # 部门表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS departments (
                    id TEXT PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # 人员表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id TEXT PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    department_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (department_code) REFERENCES departments(code)
                )
            """)

            # 报销单表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS expense_reports (
                    id TEXT PRIMARY KEY,
                    report_number TEXT UNIQUE NOT NULL,
                    department_code TEXT NOT NULL,
                    employee_code TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    total_amount REAL DEFAULT 0.0,
                    invoice_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (department_code) REFERENCES departments(code),
                    FOREIGN KEY (employee_code) REFERENCES employees(code)
                )
            """)

            # 发票表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    invoice_number TEXT NOT NULL,
                    invoice_date TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    qr_code_data TEXT,
                    report_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (report_id) REFERENCES expense_reports(id)
                )
            """)
            await db.commit()

    async def save_invoice(self, invoice: InvoiceData) -> bool:
        """保存发票数据"""
        if not invoice.id:
            invoice.id = f"{invoice.invoice_number}_{invoice.invoice_date}"

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 检查发票是否已存在
                cursor = await db.execute(
                    "SELECT id FROM invoices WHERE invoice_number = ?",
                    (invoice.invoice_number,)
                )
                existing = await cursor.fetchone()

                if existing:
                    print(f"[WARNING] 发票号重复: {invoice.invoice_number}")
                    return False  # 返回False表示发票已存在

                await db.execute("""
                    INSERT OR REPLACE INTO invoices
                    (id, invoice_number, invoice_date, total_amount, qr_code_data, report_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    invoice.id,
                    invoice.invoice_number,
                    invoice.invoice_date,
                    invoice.total_amount,
                    invoice.qr_code_data,
                    invoice.report_id,
                    invoice.created_at.isoformat()
                ))
                await db.commit()

                # 如果发票关联了报销单，更新报销单的总金额和发票数量
                if invoice.report_id:
                    await self._update_report_totals(db, invoice.report_id)

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
                    report_id=row["report_id"],
                    created_at=datetime.fromisoformat(row["created_at"])
                )
                for row in rows
            ]

    async def get_invoices_by_report(self, report_id: str) -> List[InvoiceData]:
        """获取报销单关联的所有发票"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM invoices WHERE report_id = ? ORDER BY created_at DESC",
                (report_id,)
            )
            rows = await cursor.fetchall()

            return [
                InvoiceData(
                    id=row["id"],
                    invoice_number=row["invoice_number"],
                    invoice_date=row["invoice_date"],
                    total_amount=row["total_amount"],
                    qr_code_data=row["qr_code_data"],
                    report_id=row["report_id"],
                    created_at=datetime.fromisoformat(row["created_at"])
                )
                for row in rows
            ]

    async def delete_invoice(self, invoice_id: str) -> bool:
        """删除发票"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 获取发票的report_id
                cursor = await db.execute("SELECT report_id FROM invoices WHERE id = ?", (invoice_id,))
                row = await cursor.fetchone()
                report_id = row[0] if row else None

                # 删除发票
                await db.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
                await db.commit()

                # 更新报销单统计
                if report_id:
                    await self._update_report_totals(db, report_id)

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

    # ========== 部门管理 ==========

    async def create_department(self, dept: Department) -> bool:
        """创建部门"""
        if not dept.id:
            dept.id = f"dept_{dept.code}"

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO departments (id, code, name, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    dept.id,
                    dept.code,
                    dept.name,
                    dept.created_at.isoformat()
                ))
                await db.commit()
                return True
        except Exception as e:
            print(f"创建部门失败: {e}")
            return False

    async def get_all_departments(self) -> List[Department]:
        """获取所有部门"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM departments ORDER BY code")
            rows = await cursor.fetchall()

            return [
                Department(
                    id=row["id"],
                    code=row["code"],
                    name=row["name"],
                    created_at=datetime.fromisoformat(row["created_at"])
                )
                for row in rows
            ]

    async def delete_department(self, code: str) -> bool:
        """删除部门"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM departments WHERE code = ?", (code,))
                await db.commit()
                return True
        except Exception as e:
            print(f"删除部门失败: {e}")
            return False

    # ========== 人员管理 ==========

    async def create_employee(self, emp: Employee) -> bool:
        """创建人员"""
        if not emp.id:
            emp.id = f"emp_{emp.code}"

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO employees (id, code, name, department_code, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    emp.id,
                    emp.code,
                    emp.name,
                    emp.department_code,
                    emp.created_at.isoformat()
                ))
                await db.commit()
                return True
        except Exception as e:
            print(f"创建人员失败: {e}")
            return False

    async def get_all_employees(self) -> List[Employee]:
        """获取所有人员"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT e.*, d.name as department_name
                FROM employees e
                LEFT JOIN departments d ON e.department_code = d.code
                ORDER BY e.code
            """)
            rows = await cursor.fetchall()

            return [
                Employee(
                    id=row["id"],
                    code=row["code"],
                    name=row["name"],
                    department_code=row["department_code"],
                    department_name=row["department_name"],
                    created_at=datetime.fromisoformat(row["created_at"])
                )
                for row in rows
            ]

    async def delete_employee(self, code: str) -> bool:
        """删除人员"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM employees WHERE code = ?", (code,))
                await db.commit()
                return True
        except Exception as e:
            print(f"删除人员失败: {e}")
            return False

    # ========== 报销单管理 ==========

    async def create_expense_report(self, report: ExpenseReport) -> bool:
        """创建报销单"""
        if not report.id:
            report.id = f"report_{report.report_number}"

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 获取部门和人员名称
                dept_cursor = await db.execute(
                    "SELECT name FROM departments WHERE code = ?",
                    (report.department_code,)
                )
                dept_row = await dept_cursor.fetchone()
                if dept_row:
                    report.department_name = dept_row[0]

                emp_cursor = await db.execute(
                    "SELECT name FROM employees WHERE code = ?",
                    (report.employee_code,)
                )
                emp_row = await emp_cursor.fetchone()
                if emp_row:
                    report.employee_name = emp_row[0]

                await db.execute("""
                    INSERT INTO expense_reports
                    (id, report_number, department_code, employee_code, reason, status,
                     total_amount, invoice_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    report.id,
                    report.report_number,
                    report.department_code,
                    report.employee_code,
                    report.reason,
                    report.status,
                    report.total_amount,
                    report.invoice_count,
                    report.created_at.isoformat(),
                    report.updated_at.isoformat()
                ))
                await db.commit()
                return True
        except Exception as e:
            print(f"创建报销单失败: {e}")
            return False

    async def get_all_expense_reports(self) -> List[ExpenseReport]:
        """获取所有报销单"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.*, d.name as department_name, e.name as employee_name
                FROM expense_reports r
                LEFT JOIN departments d ON r.department_code = d.code
                LEFT JOIN employees e ON r.employee_code = e.code
                ORDER BY r.created_at DESC
            """)
            rows = await cursor.fetchall()

            return [
                ExpenseReport(
                    id=row["id"],
                    report_number=row["report_number"],
                    department_code=row["department_code"],
                    department_name=row["department_name"],
                    employee_code=row["employee_code"],
                    employee_name=row["employee_name"],
                    reason=row["reason"],
                    status=row["status"],
                    total_amount=row["total_amount"],
                    invoice_count=row["invoice_count"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"])
                )
                for row in rows
            ]

    async def get_expense_report(self, report_id: str) -> Optional[ExpenseReport]:
        """获取单个报销单"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.*, d.name as department_name, e.name as employee_name
                FROM expense_reports r
                LEFT JOIN departments d ON r.department_code = d.code
                LEFT JOIN employees e ON r.employee_code = e.code
                WHERE r.id = ?
            """, (report_id,))
            row = await cursor.fetchone()

            if row:
                return ExpenseReport(
                    id=row["id"],
                    report_number=row["report_number"],
                    department_code=row["department_code"],
                    department_name=row["department_name"],
                    employee_code=row["employee_code"],
                    employee_name=row["employee_name"],
                    reason=row["reason"],
                    status=row["status"],
                    total_amount=row["total_amount"],
                    invoice_count=row["invoice_count"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"])
                )
            return None

    async def update_expense_report(self, report_id: str, report: ExpenseReport) -> bool:
        """更新报销单"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                report.updated_at = datetime.now()

                # 获取部门和人员名称
                dept_cursor = await db.execute(
                    "SELECT name FROM departments WHERE code = ?",
                    (report.department_code,)
                )
                dept_row = await dept_cursor.fetchone()
                if dept_row:
                    report.department_name = dept_row[0]

                emp_cursor = await db.execute(
                    "SELECT name FROM employees WHERE code = ?",
                    (report.employee_code,)
                )
                emp_row = await emp_cursor.fetchone()
                if emp_row:
                    report.employee_name = emp_row[0]

                await db.execute("""
                    UPDATE expense_reports
                    SET report_number = ?, department_code = ?, employee_code = ?,
                        reason = ?, status = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    report.report_number,
                    report.department_code,
                    report.employee_code,
                    report.reason,
                    report.status,
                    report.updated_at.isoformat(),
                    report_id
                ))
                await db.commit()
                return True
        except Exception as e:
            print(f"更新报销单失败: {e}")
            return False

    async def delete_expense_report(self, report_id: str) -> bool:
        """删除报销单"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 先解除关联的发票
                await db.execute(
                    "UPDATE invoices SET report_id = NULL WHERE report_id = ?",
                    (report_id,)
                )
                # 删除报销单
                await db.execute("DELETE FROM expense_reports WHERE id = ?", (report_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"删除报销单失败: {e}")
            return False

    async def _update_report_totals(self, db, report_id: str):
        """更新报销单的总金额和发票数量"""
        cursor = await db.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total
            FROM invoices WHERE report_id = ?
        """, (report_id,))
        row = await cursor.fetchone()

        await db.execute("""
            UPDATE expense_reports
            SET invoice_count = ?, total_amount = ?, updated_at = ?
            WHERE id = ?
        """, (row[0], row[1], datetime.now().isoformat(), report_id))


# 全局数据库实例
db = Database()
