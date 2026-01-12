import re
import json
from typing import Optional, Dict
import cv2
import numpy as np


class QRCodeService:
    """二维码解析服务 - 针对增值税电子发票二维码优化"""

    def __init__(self):
        # 初始化二维码检测器
        self.detector = cv2.QRCodeDetector()

    def decode_qrcode(self, image_bytes: bytes) -> Optional[Dict]:
        """解析二维码"""
        try:
            # 从字节流读取图像
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # 检测并解码二维码
            data, points, straight_qrcode = self.detector.detectAndDecode(image)

            if not data:
                return None

            # 解析二维码数据
            return self._parse_qrcode_data(data)

        except Exception as e:
            print(f"二维码解析失败: {e}")
            return None

    def _parse_invoice_qrcode(self, data: str) -> Optional[Dict]:
        """解析增值税电子发票二维码标准格式

        标准格式: 01,发票代码,发票号码,开票日期,校验码,金额
        示例: 01,1234567890,25312000000432294815,20251226,,128.50
        """
        # 清理数据，去除可能的空白字符
        data = data.strip()

        # 标准格式是以 01, 或 01， 开头
        if not data.startswith("01"):
            return None

        # 分割数据（支持中英文逗号）
        parts = re.split(r'[,，]', data)

        if len(parts) < 5:
            return None

        result = {
            "raw_data": data,
            "invoice_number": None,
            "invoice_date": None,
            "total_amount": None,
        }

        # 第三位：发票号码（20位数字）
        # 发票代码通常是12位或更少，发票号码是20位
        if len(parts) > 2:
            invoice_number = parts[2].strip()
            # 发票号码是20位数字
            if invoice_number.isdigit() and len(invoice_number) == 20:
                result["invoice_number"] = invoice_number

        # 第四位：开票日期 (YYYYMMDD)
        if len(parts) > 3:
            invoice_date = parts[3].strip()
            # 验证是否为8位数字
            if invoice_date.isdigit() and len(invoice_date) == 8:
                # 验证日期合理性
                year = invoice_date[:4]
                if year.startswith(('20', '19')):
                    result["invoice_date"] = invoice_date

        # 第六位：价税合计金额（可能存在）
        if len(parts) >= 6 and parts[5].strip():
            amount_str = parts[5].strip()
            try:
                # 去除可能的货币符号和空格
                amount_str = amount_str.replace('¥', '').replace('￥', '').replace(',', '').strip()
                if amount_str:
                    amount = float(amount_str)
                    # 合理性检查：金额应该在 0.01 - 9999999.99 之间
                    if 0.01 <= amount <= 9999999.99:
                        result["total_amount"] = amount
            except ValueError:
                pass

        # 如果至少有发票号，返回结果
        if result["invoice_number"]:
            return result

        return None

    def _parse_qrcode_data(self, data: str) -> Dict:
        """解析二维码数据 - 多格式支持"""
        # 优先尝试增值税电子发票标准格式
        invoice_result = self._parse_invoice_qrcode(data)
        if invoice_result and invoice_result.get("invoice_number"):
            return invoice_result

        result = {
            "raw_data": data,
            "invoice_number": None,
            "invoice_date": None,
            "total_amount": None,
        }

        # 尝试JSON格式解析
        try:
            json_data = json.loads(data)
            if isinstance(json_data, dict):
                result["invoice_number"] = json_data.get("invoiceNumber") or json_data.get("invoice_code") or json_data.get("发票号码")
                result["invoice_date"] = json_data.get("invoiceDate") or json_data.get("开票日期")
                result["total_amount"] = json_data.get("totalAmount") or json_data.get("amount") or json_data.get("价税合计")
                if result["invoice_number"]:
                    return result
        except json.JSONDecodeError:
            pass

        # 通用正则匹配（作为后备方案）
        # 查找发票号码 (8-20位数字)
        number_match = re.search(r'(?<!\d)(\d{8,20})(?!\d)', data)
        if number_match:
            result["invoice_number"] = number_match.group(1)

        # 查找日期 (YYYYMMDD 格式)
        date_matches = re.findall(r'\d{8}', data)
        for date_str in date_matches:
            # 确保是合理的年份
            if date_str.startswith(('20', '19')):
                # 检查月份和日期是否合理
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                if 1 <= month <= 12 and 1 <= day <= 31:
                    result["invoice_date"] = date_str
                    break

        # 查找金额 (带小数点的数字)
        amount_match = re.search(r'(\d+\.\d{2})', data)
        if amount_match:
            try:
                amount = float(amount_match.group(1))
                # 合理的金额范围（0.01 - 9999999.99）
                if 0.01 <= amount <= 9999999.99:
                    result["total_amount"] = amount
            except ValueError:
                pass

        return result


# 全局二维码服务实例
qrcode_service = QRCodeService()
