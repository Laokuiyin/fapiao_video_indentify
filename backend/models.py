from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ========== 部门相关模型 ==========

class Department(BaseModel):
    """部门模型"""
    id: Optional[str] = None
    code: str = Field(..., description="部门编码")
    name: str = Field(..., description="部门名称")
    created_at: datetime = Field(default_factory=datetime.now)


class DepartmentCreate(BaseModel):
    """创建部门请求"""
    code: str = Field(..., description="部门编码")
    name: str = Field(..., description="部门名称")


# ========== 人员相关模型 ==========

class Employee(BaseModel):
    """人员模型"""
    id: Optional[str] = None
    code: str = Field(..., description="人员编码")
    name: str = Field(..., description="姓名")
    department_code: str = Field(..., description="所属部门编码")
    department_name: Optional[str] = Field(None, description="所属部门名称")
    created_at: datetime = Field(default_factory=datetime.now)


class EmployeeCreate(BaseModel):
    """创建人员请求"""
    code: str = Field(..., description="人员编码")
    name: str = Field(..., description="姓名")
    department_code: str = Field(..., description="所属部门编码")


# ========== 报销单相关模型 ==========

class ExpenseReport(BaseModel):
    """报销单模型"""
    id: Optional[str] = None
    report_number: str = Field(..., description="报销单号")
    department_code: str = Field(..., description="部门编码")
    department_name: Optional[str] = Field(None, description="部门名称")
    employee_code: str = Field(..., description="人员编码")
    employee_name: Optional[str] = Field(None, description="人员姓名")
    reason: str = Field(..., description="报销事由")
    status: str = Field(default="draft", description="状态: draft-草稿, submitted-已提交")
    total_amount: float = Field(default=0.0, description="总金额")
    invoice_count: int = Field(default=0, description="发票数量")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ExpenseReportCreate(BaseModel):
    """创建报销单请求"""
    report_number: str = Field(..., description="报销单号")
    department_code: str = Field(..., description="部门编码")
    employee_code: str = Field(..., description="人员编码")
    reason: str = Field(..., description="报销事由")


class ExpenseReportUpdate(BaseModel):
    """更新报销单请求"""
    report_number: Optional[str] = None
    department_code: Optional[str] = None
    employee_code: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None


# ========== 发票相关模型 ==========

class InvoiceData(BaseModel):
    """发票数据模型"""
    id: Optional[str] = None
    invoice_number: str = Field(..., description="发票号码")
    invoice_date: str = Field(..., description="开票日期 YYYYMMDD")
    total_amount: float = Field(..., description="价税合计")
    qr_code_data: Optional[str] = Field(None, description="二维码原始数据")
    report_id: Optional[str] = Field(None, description="关联的报销单ID")
    created_at: datetime = Field(default_factory=datetime.now)


class InvoiceSummary(BaseModel):
    """发票汇总数据"""
    total_count: int = Field(..., description="发票总数")
    total_amount: float = Field(..., description="总金额")
    invoices: list[InvoiceData] = Field(..., description="发票列表")


# ========== 认证相关模型 ==========

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(default="", description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., description="新密码")


class QRCodeRecognizeRequest(BaseModel):
    """二维码识别请求"""
    qr_data: str = Field(..., description="二维码原始数据")
    report_id: Optional[str] = Field(None, description="关联的报销单ID")
