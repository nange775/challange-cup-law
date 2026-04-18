from typing import Any, Dict, List, Optional
import fitz  # PyMuPDF
from .base import BaseParser
from .registry import ParserRegistry

class PDFParser(BaseParser):
    supported_extensions = ['.pdf']
    supported_mimes = ['application/pdf']

    def parse(self, file_path: str, **kwargs) -> Dict[str, Any]:
        doc = fitz.open(file_path)

        all_text = []
        pages_data = []

        for page_num, page in enumerate(doc):
            text = page.get_text()
            all_text.append(text)

            # 提取图片（可选）
            images = []
            for img in page.get_images():
                images.append(img[0])  # xref

            pages_data.append({
                "page_num": page_num + 1,
                "text": text,
                "word_count": len(text),
                "image_count": len(images)
            })

        doc.close()

        full_content = "\n".join(all_text)

        # 检测文档类型
        doc_type = self._detect_document_type(full_content)

        # 提取实体
        entities = self.extract_entities(full_content)

        return {
            "content": full_content,
            "structured_data": {
                "pages": pages_data,
                "total_pages": len(pages_data),
                "total_words": sum(p["word_count"] for p in pages_data)
            },
            "metadata": {
                "doc_type": doc_type,
                "title": self._extract_title(full_content),
                "date": entities.get("dates", [None])[0]
            },
            "entities": entities,
            "type": doc_type
        }

    def _detect_document_type(self, content: str) -> str:
        """检测文档类型"""
        content_lower = content.lower()

        if any(kw in content for kw in ["笔录", "讯问", "询问", "记录"]):
            return "interrogation_record"  # 讯问/询问笔录
        elif any(kw in content for kw in ["判决书", "裁定书", "决定书"]):
            return "legal_document"  # 法律文书
        elif any(kw in content for kw in ["合同", "协议", "约定"]):
            return "contract"  # 合同协议
        elif any(kw in content for kw in ["发票", "收据", "凭证"]):
            return "invoice"  # 票据凭证
        else:
            return "general_document"  # 普通文档

    def extract_entities(self, content: str) -> Dict[str, List[str]]:
        """提取实体"""
        import re

        # 使用与Excel解析器类似的正则提取
        names = re.findall(r'[姓名当事人][:：]\s*([\u4e00-\u9fa5]{2,4})', content)
        names += re.findall(r'([\u4e00-\u9fa5]{2,3})(?:先生|女士)', content)

        amounts = re.findall(r'(\d+\.?\d*)\s*[元万元]', content)
        dates = re.findall(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?', content)

        # 地点
        locations = re.findall(r'([\u4e00-\u9fa5]{2,10}(?:市|县|区|镇|村))', content)

        return {
            "names": list(set(names)),
            "amounts": list(set(amounts)),
            "dates": list(set(dates)),
            "locations": list(set(locations))
        }

ParserRegistry.register(PDFParser())