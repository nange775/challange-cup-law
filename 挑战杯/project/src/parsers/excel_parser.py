from typing import Any, Dict, List, Optional
import pandas as pd
from .base import BaseParser
from .registry import ParserRegistry

class ExcelParser(BaseParser):
    supported_extensions = ['.xls', '.xlsx', '.xlsm']
    supported_mimes = [
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ]

    def parse(self, file_path: str, **kwargs) -> Dict[str, Any]:
        # 读取所有sheet
        xl = pd.ExcelFile(file_path)
        sheets_data = {}

        for sheet_name in xl.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            sheets_data[sheet_name] = df

        # 判断是否是财付通数据
        is_tenpay = self._detect_tenpay_format(sheets_data)

        # 提取文本内容（用于AI分析）
        content = self._dataframe_to_text(sheets_data)

        # 提取实体
        entities = self.extract_entities(content)

        return {
            "content": content,
            "structured_data": sheets_data,
            "metadata": {
                "sheets": list(sheets_data.keys()),
                "is_tenpay": is_tenpay,
                "row_counts": {k: len(v) for k, v in sheets_data.items()}
            },
            "entities": entities,
            "type": "tenpay_trades" if is_tenpay else "generic_excel"
        }

    def _detect_tenpay_format(self, sheets_data: Dict) -> bool:
        """检测是否为财付通格式"""
        for sheet_name, df in sheets_data.items():
            columns = [str(c).lower() for c in df.columns]
            # 检查财付通特征字段
            tenpay_keywords = ['交易时间', '交易类型', '交易对方', '财付通', 'tenpay']
            matches = sum(1 for kw in tenpay_keywords if any(kw in c for c in columns))
            if matches >= 2:
                return True
        return False

    def extract_entities(self, content: str) -> Dict[str, List[str]]:
        """提取实体：姓名、金额、日期等"""
        import re

        # 姓名（中文）
        names = re.findall(r'[姓名][:：]\s*([\u4e00-\u9fa5]{2,4})', content)

        # 金额（元/万元）
        amounts = re.findall(r'(\d+\.?\d*)\s*[元万元]', content)

        # 日期
        dates = re.findall(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?', content)

        # 身份证号
        idcards = re.findall(r'\d{17}[\dXx]', content)

        return {
            "names": list(set(names)),
            "amounts": list(set(amounts)),
            "dates": list(set(dates)),
            "idcards": list(set(idcards))
        }

# 注册解析器
ParserRegistry.register(ExcelParser())