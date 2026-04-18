from abc import ABC, abstractmethod
from typing import Any, Dict, List
import pandas as pd

class BaseParser(ABC):
    """解析器基类"""

    supported_extensions: List[str] = []
    supported_mimes: List[str] = []

    @abstractmethod
    def parse(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        解析文件内容
        Returns: {
            "content": str,           # 原始文本内容
            "structured_data": Any,   # 结构化数据(如DataFrame)
            "metadata": dict,         # 文件元数据
            "entities": list          # 提取的实体(人名、金额等)
        }
        """
        pass

    @abstractmethod
    def extract_entities(self, content: str) -> Dict[str, List[str]]:
        """提取实体：人名、地名、金额、日期等"""
        pass