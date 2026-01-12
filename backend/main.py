from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from .database import db
from .ocr_service import ocr_service
from .qrcode_service import qrcode_service
from .models import InvoiceData, InvoiceSummary


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


@app.post("/api/recognize")
async def recognize_invoice(file: UploadFile = File(...)):
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
async def get_invoices():
    """获取所有发票"""
    invoices = await db.get_all_invoices()
    total_amount = sum(inv.total_amount for inv in invoices)

    return InvoiceSummary(
        total_count=len(invoices),
        total_amount=total_amount,
        invoices=invoices
    )


@app.delete("/api/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str):
    """删除发票"""
    success = await db.delete_invoice(invoice_id)
    if success:
        await broadcast_update()
        return {"success": True}
    return {"success": False, "message": "删除失败"}


@app.delete("/api/invoices")
async def clear_all_invoices():
    """清空所有发票"""
    success = await db.clear_all()
    if success:
        await broadcast_update()
        return {"success": True}
    return {"success": False, "message": "清空失败"}


async def broadcast_update():
    """广播数据更新"""
    summary = await get_invoices()
    await manager.broadcast({
        "type": "update",
        "data": summary.model_dump()
    })


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
