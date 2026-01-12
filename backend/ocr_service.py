import re
import cv2
import numpy as np
from paddleocr import PaddleOCR
from typing import Optional, Dict, List, Tuple


class OCRService:
    """OCR识别服务 - 针对电子发票标准版式优化"""

    def __init__(self):
        # 初始化 PaddleOCR，使用中文模型
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            show_log=False,
            use_gpu=False  # 如需GPU加速可设为True
        )

    def preprocess_image(self, image_bytes: bytes) -> np.ndarray:
        """图像预处理"""
        # 从字节流读取图像
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 转换为灰度图
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 自适应阈值处理，增强文字对比度
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        return binary, image  # 返回二值图和原图

    def detect_qr_position(self, image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """检测二维码位置，返回 (x, y, w, h)"""
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(image)

        if points is not None:
            # points 是二维码的四个角点
            points = points.astype(int)
            # 计算边界框
            x_min = int(points[:, 0].min())
            y_min = int(points[:, 1].min())
            x_max = int(points[:, 0].max())
            y_max = int(points[:, 1].max())
            return (x_min, y_min, x_max - x_min, y_max - y_min)

        return None

    def extract_top_right_region(self, image: np.ndarray, qr_rect: Tuple[int, int, int, int]) -> np.ndarray:
        """提取右上角区域（发票号和开票日期）

        电子发票版式：二维码在左上角，发票号和日期在右上角
        """
        h, w = image.shape[:2]
        qr_x, qr_y, qr_w, qr_h = qr_rect

        # 右上角区域：从图片中间到右边，高度与二维码区域相当
        top_right_y_start = 0
        top_right_y_end = int(qr_y + qr_h * 2)  # 右上角区域约为二维码高度的2倍
        top_right_x_start = int(w // 2)  # 从图片中间开始
        top_right_x_end = w

        # 确保不越界
        top_right_y_end = min(top_right_y_end, h)
        top_right_x_start = max(0, top_right_x_start)

        return image[top_right_y_start:top_right_y_end, top_right_x_start:top_right_x_end]

    def extract_bottom_region(self, image: np.ndarray) -> np.ndarray:
        """提取底部区域（价税合计）

        电子发票版式：价税合计在备注上面一行
        """
        h, w = image.shape[:2]

        # 取图片下半部分
        bottom_region = image[int(h * 0.6):, :]  # 从60%高度开始到底部

        return bottom_region

    def extract_invoice_number(self, text_lines: List[str]) -> Optional[str]:
        """从文本中提取发票号码"""
        full_text = "\n".join(text_lines)

        # 发票号码匹配模式
        patterns = [
            r'发票号码[：:]\s*(\d{8,})',
            r'号码[：:]\s*(\d{8,})',
            r'No\.?\s*[：:]?\s*(\d{8,})',
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text)
            if match:
                return match.group(1)

        # 尝试找8-20位纯数字（通常发票号在右上角单独出现）
        for line in text_lines:
            line = line.strip()
            # 纯数字行，长度8-20位
            if re.match(r'^\d{8,20}$', line):
                return line

        return None

    def extract_invoice_date(self, text_lines: List[str]) -> Optional[str]:
        """从文本中提取开票日期"""
        full_text = "\n".join(text_lines)

        # 日期匹配模式
        patterns = [
            r'开票日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})日?',
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text)
            if match:
                if len(match.groups()) == 3:
                    year, month, day = match.groups()
                    return f"{year}{month.zfill(2)}{day.zfill(2)}"

        return None

    def extract_total_amount(self, text_lines: List[str]) -> Optional[float]:
        """从文本中提取价税合计"""
        full_text = "\n".join(text_lines)

        # 价税合计匹配模式 - 按优先级排序
        patterns = [
            # 完整格式：价税合计（小写）：¥123.45
            r'价税合计[（(]*小写[）)]?\s*[：:]?\s*[￥¥]?\s*([0-9,]+\.?\d*)',
            # 简化格式：价税合计：¥123.45
            r'价税合计\s*[：:]\s*[￥¥]?\s*([0-9,]+\.?\d{2})',
            # 变体：合计（小写）：123.45
            r'合计[（(]*小写[）)]?\s*[：:]?\s*[￥¥]?\s*([0-9,]+\.?\d{2})',
            # 简化：合计：123.45
            r'合计\s*[：:]\s*[￥¥]?\s*([0-9,]+\.?\d{2})',
            # 备注上方常见格式：（小写）¥123.45
            r'[（(]小写[）)]\s*[￥¥]\s*([0-9,]+\.?\d{2})',
            # 纯金额带货币符号
            r'[￥¥]\s*([0-9,]+\.\d{2})',
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text)
            if match:
                amount_str = match.group(1).replace(',', '').strip()
                try:
                    amount = float(amount_str)
                    # 合理性检查：0.01 - 9999999.99
                    if 0.01 <= amount <= 9999999.99:
                        return amount
                except ValueError:
                    continue

        return None

    def recognize_region(self, image: np.ndarray) -> List[str]:
        """对指定区域进行OCR识别"""
        result = self.ocr.ocr(image, cls=True)
        text_lines = []

        if result and result[0]:
            for line in result[0]:
                if line[1] and line[1][0]:
                    text_lines.append(line[1][0])

        return text_lines

    def recognize(self, image_bytes: bytes) -> Dict[str, Optional[str]]:
        """识别发票图片 - 针对电子发票标准版式"""
        try:
            # 预处理图像
            binary_img, color_img = self.preprocess_image(image_bytes)

            # 1. 检测二维码位置
            qr_rect = self.detect_qr_position(color_img)

            invoice_number = None
            invoice_date = None
            total_amount = None

            # 2. 如果检测到二维码，精确定位右上角区域
            if qr_rect:
                # 提取右上角区域（发票号和日期）
                top_right_region = self.extract_top_right_region(color_img, qr_rect)
                top_right_lines = self.recognize_region(top_right_region)

                invoice_number = self.extract_invoice_number(top_right_lines)
                invoice_date = self.extract_invoice_date(top_right_lines)
            else:
                # 未检测到二维码，对整个图片进行OCR
                all_lines = self.recognize_region(binary_img)
                invoice_number = self.extract_invoice_number(all_lines)
                invoice_date = self.extract_invoice_date(all_lines)

            # 3. 提取底部区域识别价税合计
            if not total_amount:
                bottom_region = self.extract_bottom_region(color_img)
                bottom_lines = self.recognize_region(bottom_region)
                total_amount = self.extract_total_amount(bottom_lines)

            # 如果底部没找到，尝试全图识别
            if not total_amount:
                all_lines = self.recognize_region(binary_img)
                total_amount = self.extract_total_amount(all_lines)

            return {
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "total_amount": total_amount,
            }

        except Exception as e:
            print(f"OCR识别失败: {e}")
            return {
                "invoice_number": None,
                "invoice_date": None,
                "total_amount": None,
            }


# 全局OCR服务实例
ocr_service = OCRService()
