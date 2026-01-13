from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
import os
from .database import db
from .ocr_service import ocr_service
from .qrcode_service import qrcode_service
from .auth import auth_manager
from .models import (
    InvoiceData, InvoiceSummary,
    LoginRequest, LoginResponse, ChangePasswordRequest,
    QRCodeRecognizeRequest,
    Department, DepartmentCreate,
    Employee, EmployeeCreate,
    ExpenseReport, ExpenseReportCreate, ExpenseReportUpdate
)


app = FastAPI(title="发票识别系统")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# HTTP Bearer 认证
security = HTTPBearer()


# ========== 认证相关函数 ==========

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """获取当前登录用户"""
    from jose import JWTError
    from .auth import SECRET_KEY, ALGORITHM

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        from jose import jwt
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    return username


# ========== 数据库和连接管理 ==========

class ConnectionManager:
    """WebSocket连接管理"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """广播消息到所有连接的客户端"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


@app.on_event("startup")
async def startup():
    """启动时初始化数据库"""
    await db.init_db()
    await auth_manager.init_db()


# ========== 页面路由 ==========

@app.get("/login")
async def login_page():
    """登录页面"""
    with open("frontend/login.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/")
async def root():
    """根路径重定向到PC端页面"""
    with open("frontend/pc/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/mobile")
async def mobile():
    """手机端采集页面"""
    with open("frontend/mobile/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ========== 认证 API ==========

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """用户登录"""
    user = await auth_manager.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    access_token = auth_manager.create_access_token(
        data={"sub": user["username"]}
    )

    return LoginResponse(access_token=access_token)


@app.post("/api/auth/change-password")
async def change_password(
    request: ChangePasswordRequest,
    username: str = Depends(get_current_user)
):
    """修改密码"""
    success = await auth_manager.change_password(username, request.old_password, request.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    return {"success": True, "message": "密码修改成功"}


# ========== WebSocket ==========

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket连接端点"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # 处理客户端消息
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ========== 发票 API（需要认证）==========

@app.post("/api/recognize-qrcode")
async def recognize_qrcode(
    request: QRCodeRecognizeRequest,
    username: str = Depends(get_current_user)
):
    """直接识别二维码数据"""
    print(f"[DEBUG] 收到扫描请求 - QR数据: {request.qr_data[:50]}..., 报销单ID: {request.report_id}")

    # 解析二维码数据
    qr_result = qrcode_service.decode_qrcode_text(request.qr_data)
    print(f"[DEBUG] 解析结果: {qr_result}")

    if not qr_result or not qr_result.get("invoice_number"):
        print("[DEBUG] 解析失败，无法识别发票号码")
        return {
            "success": False,
            "message": "无法识别二维码，请确保是有效的发票二维码"
        }

    # 构建发票数据（使用请求中的 report_id）
    invoice_data = InvoiceData(
        invoice_number=qr_result["invoice_number"],
        invoice_date=qr_result.get("invoice_date") or "",
        total_amount=qr_result.get("total_amount") or 0.0,
        qr_code_data=qr_result.get("raw_data"),
        report_id=request.report_id
    )

    print(f"[DEBUG] 准备保存发票 - 号码: {invoice_data.invoice_number}, 报销单: {invoice_data.report_id}")

    # 保存到数据库
    success = await db.save_invoice(invoice_data)
    if success:
        print(f"[DEBUG] 保存成功")
        # 广播更新
        await broadcast_update()
        return {
            "success": True,
            "data": invoice_data.model_dump()
        }

    # 检查是否是重复发票
    existing_invoices = await db.get_all_invoices()
    invoice_exists = any(inv.invoice_number == invoice_data.invoice_number for inv in existing_invoices)

    if invoice_exists:
        print(f"[DEBUG] 发票号重复: {invoice_data.invoice_number}")
        return {
            "success": False,
            "message": f"发票号码 {invoice_data.invoice_number} 已存在，请勿重复扫描",
            "duplicate": True
        }

    print(f"[DEBUG] 保存失败")
    return {
        "success": False,
        "message": "保存失败"
    }


@app.post("/api/recognize")
async def recognize_invoice(
    file: UploadFile = File(...),
    username: str = Depends(get_current_user)
):
    """识别发票图片 - 二维码和OCR互补"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    image_bytes = await file.read()

    # 同时进行二维码解析和OCR识别
    qr_result = qrcode_service.decode_qrcode(image_bytes)
    ocr_result = ocr_service.recognize(image_bytes)

    # 合并结果：二维码优先，OCR补充缺失字段
    invoice_number = None
    invoice_date = None
    total_amount = None
    qr_code_data = None

    # 1. 发票号：二维码优先，OCR补充
    if qr_result and qr_result.get("invoice_number"):
        invoice_number = qr_result["invoice_number"]
        qr_code_data = qr_result.get("raw_data")
    elif ocr_result.get("invoice_number"):
        invoice_number = ocr_result["invoice_number"]

    # 2. 开票日期：二维码优先，OCR补充
    if qr_result and qr_result.get("invoice_date"):
        invoice_date = qr_result["invoice_date"]
    elif ocr_result.get("invoice_date"):
        invoice_date = ocr_result["invoice_date"]

    # 3. 价税合计：二维码优先（更准确），OCR补充
    if qr_result and qr_result.get("total_amount") is not None:
        total_amount = qr_result["total_amount"]
    elif ocr_result.get("total_amount") is not None:
        total_amount = ocr_result["total_amount"]

    # 必须有发票号才认为识别成功
    if not invoice_number:
        return {
            "success": False,
            "message": "识别失败，请确保图片清晰",
            "debug": {
                "qr_result": qr_result,
                "ocr_result": ocr_result
            }
        }

    # 构建发票数据
    invoice_data = InvoiceData(
        invoice_number=invoice_number,
        invoice_date=invoice_date or "",
        total_amount=total_amount or 0.0,
        qr_code_data=qr_code_data
    )

    # 保存到数据库
    success = await db.save_invoice(invoice_data)
    if success:
        # 广播更新
        await broadcast_update()
        return {
            "success": True,
            "data": invoice_data.model_dump()
        }

    return {
        "success": False,
        "message": "保存失败"
    }


@app.get("/api/invoices")
async def get_invoices(username: str = Depends(get_current_user)):
    """获取所有发票"""
    invoices = await db.get_all_invoices()
    total_amount = sum(inv.total_amount for inv in invoices)

    return InvoiceSummary(
        total_count=len(invoices),
        total_amount=total_amount,
        invoices=invoices
    )


@app.delete("/api/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, username: str = Depends(get_current_user)):
    """删除发票"""
    success = await db.delete_invoice(invoice_id)
    if success:
        await broadcast_update()
        return {"success": True}
    return {"success": False, "message": "删除失败"}


@app.delete("/api/invoices")
async def clear_all_invoices(username: str = Depends(get_current_user)):
    """清空所有发票"""
    success = await db.clear_all()
    if success:
        await broadcast_update()
        return {"success": True}
    return {"success": False, "message": "清空失败"}


# ========== 部门管理 API ==========

@app.get("/api/departments")
async def get_departments(username: str = Depends(get_current_user)):
    """获取所有部门"""
    departments = await db.get_all_departments()
    return {"success": True, "data": departments}


@app.post("/api/departments")
async def create_department(
    request: DepartmentCreate,
    username: str = Depends(get_current_user)
):
    """创建部门"""
    dept = Department(**request.model_dump())
    success = await db.create_department(dept)
    if success:
        return {"success": True, "data": dept.model_dump()}
    return {"success": False, "message": "创建失败"}


@app.delete("/api/departments/{code}")
async def delete_department(code: str, username: str = Depends(get_current_user)):
    """删除部门"""
    success = await db.delete_department(code)
    if success:
        return {"success": True}
    return {"success": False, "message": "删除失败"}


# ========== 人员管理 API ==========

@app.get("/api/employees")
async def get_employees(username: str = Depends(get_current_user)):
    """获取所有人员"""
    employees = await db.get_all_employees()
    return {"success": True, "data": employees}


@app.post("/api/employees")
async def create_employee(
    request: EmployeeCreate,
    username: str = Depends(get_current_user)
):
    """创建人员"""
    emp = Employee(**request.model_dump())
    success = await db.create_employee(emp)
    if success:
        return {"success": True, "data": emp.model_dump()}
    return {"success": False, "message": "创建失败"}


@app.delete("/api/employees/{code}")
async def delete_employee(code: str, username: str = Depends(get_current_user)):
    """删除人员"""
    success = await db.delete_employee(code)
    if success:
        return {"success": True}
    return {"success": False, "message": "删除失败"}


# ========== 报销单管理 API ==========

@app.get("/api/expense-reports")
async def get_expense_reports(username: str = Depends(get_current_user)):
    """获取所有报销单"""
    reports = await db.get_all_expense_reports()
    return {"success": True, "data": reports}


@app.get("/api/expense-reports/{report_id}")
async def get_expense_report(report_id: str, username: str = Depends(get_current_user)):
    """获取单个报销单及其发票"""
    report = await db.get_expense_report(report_id)
    if report:
        invoices = await db.get_invoices_by_report(report_id)
        return {
            "success": True,
            "data": {
                "report": report.model_dump(),
                "invoices": [inv.model_dump() for inv in invoices]
            }
        }
    return {"success": False, "message": "报销单不存在"}


@app.post("/api/expense-reports")
async def create_expense_report(
    request: ExpenseReportCreate,
    username: str = Depends(get_current_user)
):
    """创建报销单"""
    report = ExpenseReport(**request.model_dump())
    success = await db.create_expense_report(report)
    if success:
        return {"success": True, "data": report.model_dump()}
    return {"success": False, "message": "创建失败"}


@app.put("/api/expense-reports/{report_id}")
async def update_expense_report(
    report_id: str,
    request: ExpenseReportUpdate,
    username: str = Depends(get_current_user)
):
    """更新报销单"""
    report = await db.get_expense_report(report_id)
    if not report:
        return {"success": False, "message": "报销单不存在"}

    # 更新字段
    if request.report_number is not None:
        report.report_number = request.report_number
    if request.department_code is not None:
        report.department_code = request.department_code
    if request.employee_code is not None:
        report.employee_code = request.employee_code
    if request.reason is not None:
        report.reason = request.reason
    if request.status is not None:
        report.status = request.status

    success = await db.update_expense_report(report_id, report)
    if success:
        return {"success": True, "data": report.model_dump()}
    return {"success": False, "message": "更新失败"}


@app.delete("/api/expense-reports/{report_id}")
async def delete_expense_report(report_id: str, username: str = Depends(get_current_user)):
    """删除报销单"""
    success = await db.delete_expense_report(report_id)
    if success:
        return {"success": True}
    return {"success": False, "message": "删除失败"}


@app.post("/api/expense-reports/{report_id}/submit")
async def submit_expense_report(report_id: str, username: str = Depends(get_current_user)):
    """提交报销单"""
    report = await db.get_expense_report(report_id)
    if not report:
        return {"success": False, "message": "报销单不存在"}

    report.status = "submitted"
    success = await db.update_expense_report(report_id, report)
    if success:
        return {"success": True, "data": report.model_dump()}
    return {"success": False, "message": "提交失败"}


async def broadcast_update():
    """广播数据更新"""
    summary = await get_invoices("admin")  # 广播时使用默认用户
    await manager.broadcast({
        "type": "update",
        "data": summary.model_dump()
    })


if __name__ == "__main__":
    import ssl

    # 检查SSL证书是否存在
    cert_file = "cert.pem"
    key_file = "key.pem"

    if os.path.exists(cert_file) and os.path.exists(key_file):
        # 使用HTTPS
        print("🔒 使用 HTTPS 模式启动...")
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8000,
            ssl_keyfile=key_file,
            ssl_certfile=cert_file,
            reload=True
        )
    else:
        # 使用HTTP
        print("⚠️  SSL证书未找到，使用 HTTP 模式（摄像头功能将不可用）")
        print("💡 生成证书: openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes")
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True
        )
