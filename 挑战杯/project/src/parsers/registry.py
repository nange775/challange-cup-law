from typing import Any, Dict, List, Optional  # 修复：添加 Optional 导入
from .base import BaseParser
from pathlib import Path
class ParserRegistry:
    """解析器注册表"""
    _parsers: Dict[str, BaseParser] = {}

    @classmethod
    def register(cls, parser: BaseParser):
        for ext in parser.supported_extensions:
            cls._parsers[ext.lower()] = parser
        return parser

    @classmethod
    def get_parser(cls, file_path: str) -> Optional[BaseParser]:
        ext = Path(file_path).suffix.lower()
        return cls._parsers.get(ext)

    @classmethod
    def supported_formats(cls) -> List[str]:
        return list(cls._parsers.keys())