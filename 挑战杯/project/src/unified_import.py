from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
import shutil
import json
import pandas as pd

from .parsers.registry import ParserRegistry
from .database import create_evidence, get_conn
from .evidence_import import import_evidence


class UnifiedImportService:
    """统一导入服务"""

    def __init__(self, case_id: int, uploader: str = "system"):
        self.case_id = case_id
        self.uploader = uploader
        self.evidence_files_dir = Path("data/evidence_files")
        self.evidence_files_dir.mkdir(parents=True, exist_ok=True)

    def import_file(self, file_path: str, evidence_type: str = "auto",
                    description: str = "") -> Dict[str, Any]:
        """
        统一导入入口

        Args:
            file_path: 文件路径
            evidence_type: 证据类型 (auto=自动识别)
            description: 证据描述
        """
        path = Path(file_path)

        # 1. 计算文件指纹
        file_hash = self._calculate_hash(path)

        # 2. 检查重复
        existing = self._check_duplicate(file_hash)
        if existing:
            return {"status": "duplicate", "evidence_id": existing}

        # 3. 获取解析器
        parser = ParserRegistry.get_parser(str(path))
        if not parser:
            return {"status": "error", "message": f"不支持的文件格式: {path.suffix}"}

        # 4. 解析文件
        try:
            parse_result = parser.parse(str(path))
        except Exception as e:
            return {"status": "error", "message": f"解析失败: {str(e)}"}

        # 5. 自动识别证据类型
        if evidence_type == "auto":
            evidence_type = self._auto_detect_type(parse_result)

        # 6. 保存文件到证据目录
        evidence_id = self._save_file(path, file_hash, parse_result)

        # 7. 存储元数据到数据库
        self._save_metadata(evidence_id, path, evidence_type, description,
                            parse_result, file_hash)

        # 8. 结构化数据导入专门表
        self._import_structured_data(evidence_id, evidence_type, parse_result)

        # 9. 自动关联人员
        self._auto_link_persons(evidence_id, parse_result)

        return {
            "status": "success",
            "evidence_id": evidence_id,
            "type": evidence_type,
            "entities": parse_result.get("entities", {}),
            "metadata": parse_result.get("metadata", {})
        }

    def _calculate_hash(self, path: Path) -> str:
        """计算文件MD5"""
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _check_duplicate(self, file_hash: str) -> Optional[int]:
        """检查是否已存在相同文件"""
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT evidence_id FROM evidence_meta WHERE file_hash = ?",
            (file_hash,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def _auto_detect_type(self, parse_result: Dict) -> str:
        """根据解析结果自动识别证据类型"""
        content = parse_result.get("content", "")
        metadata = parse_result.get("metadata", {})

        # 根据类型字段判断
        doc_type = metadata.get("doc_type", "")

        type_mapping = {
            "tenpay_trades": "transaction_flow",  # 交易流水
            "interrogation_record": "interrogation",  # 讯问笔录
            "legal_document": "legal_doc",  # 法律文书
            "contract": "contract",  # 合同协议
            "invoice": "invoice",  # 票据
            "word_document": "document",  # 普通文档
            "generic_excel": "spreadsheet",  # 普通表格
        }

        return type_mapping.get(doc_type, "other")

    def _save_file(self, path: Path, file_hash: str, parse_result: Dict) -> int:
        """保存文件到证据目录"""
        # 生成证据ID（时间戳 + 哈希前8位）
        import time
        evidence_id = f"EV{int(time.time())}{file_hash[:8].upper()}"

        # 目标目录
        case_dir = self.evidence_files_dir / str(self.case_id)
        case_dir.mkdir(parents=True, exist_ok=True)

        # 保存文件
        dest_path = case_dir / f"{evidence_id}_{path.name}"
        shutil.copy2(path, dest_path)

        return evidence_id

    def _save_metadata(self, evidence_id: str, path: Path, evidence_type: str,
                    description: str, parse_result: Dict, file_hash: str):
        """保存元数据到数据库"""
        metadata = parse_result.get("metadata", {})
        entities = parse_result.get("entities", {})

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO evidence_meta (
                evidence_id, case_id, filename, file_type, file_size,
                file_hash, evidence_type, description, upload_time,
                uploader, metadata_json, entities_json, content_preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)
        """, (
            evidence_id,
            self.case_id,
            path.name,
            path.suffix.lower(),
            path.stat().st_size,
            file_hash,
            evidence_type,
            description,
            self.uploader,
            json.dumps(metadata, ensure_ascii=False),
            json.dumps(entities, ensure_ascii=False),
            parse_result.get("content", "")[:1000]  # 前1000字预览
        ))

        conn.commit()
        conn.close()

    def _import_structured_data(self, evidence_id: str, evidence_type: str,
                                parse_result: Dict):
        """将结构化数据导入专门表"""
        if evidence_type == "transaction_flow":
            # 交易流水 -> transactions 表
            structured = parse_result.get("structured_data", {})
            # 调用现有的财付通导入逻辑
            for sheet_name, df in structured.items():
                if "交易" in sheet_name or "trade" in sheet_name.lower():
                    self._import_transaction_data(evidence_id, df)

        elif evidence_type == "interrogation":
            # 讯问笔录 -> interrogation_records 表
            content = parse_result.get("content", "")
            self._import_interrogation_data(evidence_id, content)

        elif evidence_type in ["contract", "legal_doc"]:
            # 合同/文书 -> legal_documents 表
            metadata = parse_result.get("metadata", {})
            self._import_legal_document(evidence_id, metadata)

    def _import_transaction_data(self, evidence_id: str, df: pd.DataFrame):
        """导入交易数据"""
        # 复用现有的 ingest.py 逻辑
        from .ingest import process_tenpay_trades
        # 关联 evidence_id
        process_tenpay_trades(df, source_evidence_id=evidence_id)

    def _auto_link_persons(self, evidence_id: str, parse_result: Dict):
        """自动关联人员"""
        entities = parse_result.get("entities", {})
        names = entities.get("names", [])
        idcards = entities.get("idcards", [])

        conn = get_conn()
        cursor = conn.cursor()

        # 根据身份证号精确匹配
        for idcard in idcards:
            cursor.execute(
                "SELECT id FROM persons WHERE idcard = ?",
                (idcard,)
            )
            result = cursor.fetchone()
            if result:
                person_id = result[0]
                # 创建证据-人员关联
                cursor.execute("""
                    INSERT OR IGNORE INTO evidence_person_links
                    (evidence_id, person_id, link_type, confidence)
                    VALUES (?, ?, 'auto_idcard', 1.0)
                """, (evidence_id, person_id))

        # 根据姓名模糊匹配（需人工确认）
        for name in names:
            cursor.execute(
                "SELECT id FROM persons WHERE real_name LIKE ? OR wechat_nickname LIKE ?",
                (f"%{name}%", f"%{name}%")
            )
            results = cursor.fetchall()
            for (person_id,) in results:
                cursor.execute("""
                    INSERT OR IGNORE INTO evidence_person_links
                    (evidence_id, person_id, link_type, confidence)
                    VALUES (?, ?, 'auto_name', 0.5)
                """, (evidence_id, person_id))

        conn.commit()
        conn.close()