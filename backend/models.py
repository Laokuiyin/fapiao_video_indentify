from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class InvoiceData(BaseModel):
    """发票数据模型"""
    id: Optional[str] = None
    invoice_number: str = Field(..., description="发票号码")
    invoice_date: str = Field(..., description="开票日期 YYYYMMDD")
    total_amount: float = Field(..., description="价税合计")
    qr_code_data: Optional[str] = Field(None, description="二维码原始数据")
    created_at: datetime = Field(default_factory=datetime.now)


class InvoiceSummary(BaseModel):
    """发票汇总数据"""
    total_count: int = Field(..., description="发票总数")
    total_amount: float = Field(..., description="总金额")
    invoices: list[InvoiceData] = Field(..., description="发票列表")
