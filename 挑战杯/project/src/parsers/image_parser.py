"""图像解析器 - 支持扫描件OCR识别"""
import io
from pathlib import Path
from typing import Any, Dict, List
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.parsers.base import BaseParser
from src.parsers.registry import ParserRegistry


class ImageParser(BaseParser):
    """图像解析器 - OCR文字识别"""

    supported_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
    supported_mimes = [
        'image/jpeg',
        'image/png',
        'image/bmp',
        'image/tiff',
    ]

    def __init__(self):
        self.ocr_available = self._check_ocr()

    def _check_ocr(self) -> bool:
        """检查OCR是否可用"""
        try:
            from PIL import Image
            import pytesseract
            return True
        except ImportError:
            return False

    def parse(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        解析图像文件并进行OCR识别
        """
        path = Path(file_path)

        # 检查OCR依赖
        if not self.ocr_available:
            return {
                "content": "",
                "structured_data": {"ocr_available": False},
                "metadata": {
                    "filename": path.name,
                    "error": "OCR不可用，请安装 pytesseract 和 Pillow"
                },
                "entities": {},
                "type": "image_unavailable"
            }

        try:
            from PIL import Image
            import pytesseract

            # 打开图像
            image = Image.open(file_path)

            # 获取图像信息
            image_info = {
                "format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
                "filename": path.name
            }

            # 图像预处理以提高OCR准确性
            processed_image = self._preprocess_image(image)

            # 执行OCR识别（中英文混合）
            ocr_text = pytesseract.image_to_string(
                processed_image,
                lang='chi_sim+eng'  # 简体中文+英文
            )

            # 清理OCR文本
            ocr_text = self._clean_ocr_text(ocr_text)

            # 提取实体
            entities = self.extract_entities(ocr_text)

            # 尝试识别文档类型
            doc_type = self._detect_document_type(ocr_text)

            return {
                "content": ocr_text,
                "structured_data": {
                    "image_info": image_info,
                    "ocr_available": True,
                    "ocr_confidence": "medium"  # Tesseract不提供简单置信度，此处为占位
                },
                "metadata": {
                    "filename": path.name,
                    "doc_type": doc_type,
                    "title": f"扫描件: {path.stem}",
                    "dimensions": f"{image.width}x{image.height}"
                },
                "entities": entities,
                "type": doc_type if doc_type != "general_document" else "scanned_document"
            }

        except Exception as e:
            return {
                "content": "",
                "structured_data": {"ocr_available": False, "error": str(e)},
                "metadata": {
                    "filename": path.name,
                    "error": str(e)
                },
                "entities": {},
                "type": "image_error"
            }

    def _preprocess_image(self, image) -> Any:
        """
        图像预处理以提高OCR准确性
        """
        from PIL import Image, ImageEnhance, ImageFilter

        # 转换为RGB（如果是RGBA或其他模式）
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # 增加对比度
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        # 轻微锐化
        image = image.filter(ImageFilter.SHARPEN)

        # 如果图像较小，进行放大以提高识别率
        width, height = image.size
        if width < 1000 or height < 1000:
            scale = max(2, 2000 // max(width, height))
            new_size = (width * scale, height * scale)
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        return image

    def _clean_ocr_text(self, text: str) -> str:
        """
        清理OCR识别结果
        """
        import re

        # 移除多余的空白行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        # 移除控制字符
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)

        # 统一空格
        text = re.sub(r' +', ' ', text)

        return text.strip()

    def _detect_document_type(self, content: str) -> str:
        """
        根据OCR内容检测文档类型
        """
        content_lower = content.lower()

        keywords = {
            'interrogation_record': ['笔录', '讯问', '询问', '记录', '答', '问：'],
            'legal_document': ['判决书', '裁定书', '决定书', '起诉书', '本院'],
            'contract': ['合同', '协议', '约定', '甲方', '乙方'],
            'invoice': ['发票', '收据', '凭证', '金额', '开票'],
            'statement': ['供述', '交代', '承认', '辩解'],
            'testimony': ['证言', '证实', '看到', '听到'],
            'appraisal': ['鉴定', '检验', '检测', '结论'],
        }

        scores = {doc_type: 0 for doc_type in keywords}
        for doc_type, words in keywords.items():
            for word in words:
                if word in content or word in content_lower:
                    scores[doc_type] += 1

        if max(scores.values()) > 0:
            return max(scores, key=scores.get)

        return "scanned_document"

    def extract_entities(self, content: str) -> Dict[str, List[str]]:
        """
        从OCR文本中提取实体
        """
        import re

        # 姓名（中文）
        names = re.findall(r'[姓名当事人][:：]\s*([\u4e00-\u9fa5]{2,4})', content)
        names += re.findall(r'([\u4e00-\u9fa5]{2,3})(?:先生|女士|同志)', content)

        # 金额
        amounts = re.findall(r'(\d+\.?\d*)\s*[元万元]', content)

        # 日期
        dates = re.findall(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?', content)

        # 身份证号
        idcards = re.findall(r'\d{17}[\dXx]', content)

        # 电话号码
        phones = re.findall(r'1[3-9]\d{9}', content)

        return {
            "names": list(set(names)),
            "amounts": list(set(amounts)),
            "dates": list(set(dates)),
            "idcards": list(set(idcards)),
            "phones": list(set(phones))
        }


# 注册解析器
ParserRegistry.register(ImageParser())
