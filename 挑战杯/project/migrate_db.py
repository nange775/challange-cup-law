"""数据库迁移脚本 - 从旧结构迁移到新结构"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/investigation.db")
BACKUP_PATH = Path(f"data/investigation_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")


def backup_database():
    """备份数据库"""
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✓ 数据库已备份到: {BACKUP_PATH}")
        return True
    return False


def migrate():
    """执行迁移"""
    print("开始数据库迁移...")

    # 1. 备份
    has_data = backup_database()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if has_data:
        # 2. 读取旧数据
        print("✓ 读取旧数据...")
        old_persons = cursor.execute("SELECT * FROM persons").fetchall()
        old_transactions = cursor.execute("SELECT * FROM transactions").fetchall()
        try:
            old_bank_cards = cursor.execute("SELECT * FROM bank_cards").fetchall()
        except:
            old_bank_cards = []

        # 3. 删除旧表
        print("✓ 删除旧表...")
        cursor.execute("DROP TABLE IF EXISTS transactions")
        cursor.execute("DROP TABLE IF EXISTS bank_cards")
        cursor.execute("DROP TABLE IF EXISTS persons")

    # 4. 创建新表结构
    print("✓ 创建新表结构...")
    from src.database import init_db
    conn.close()
    init_db()

    if has_data:
        # 5. 创建默认案件
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        print("✓ 创建默认案件...")
        default_case_id = "CASE_DEFAULT"
        cursor.execute(
            "INSERT INTO cases (case_id, case_name) VALUES (?, ?)",
            [default_case_id, "历史数据（自动迁移）"]
        )

        # 6. 迁移人员数据
        print(f"✓ 迁移 {len(old_persons)} 条人员数据...")
        for person in old_persons:
            cursor.execute("""
                INSERT INTO persons (user_id, case_id, name, id_card, phone, reg_time, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [person[0], default_case_id, person[1], person[2], person[3], person[4], '嫌疑人'])

        # 7. 迁移银行卡数据
        if old_bank_cards:
            print(f"✓ 迁移 {len(old_bank_cards)} 条银行卡数据...")
            for card in old_bank_cards:
                cursor.execute("""
                    INSERT INTO bank_cards (id, user_id, card_no, bank_name, status)
                    VALUES (?, ?, ?, ?, ?)
                """, card)

        # 8. 迁移交易数据
        print(f"✓ 迁移 {len(old_transactions)} 条交易数据...")
        for tx in old_transactions:
            cursor.execute("""
                INSERT INTO transactions
                (id, case_id, evidence_id, trade_no, big_trade_no, user_id, user_name,
                 direction, biz_type, purpose, trade_time, amount, balance, user_card,
                 counterpart_id, counterpart_name, counterpart_card, counterpart_bank, remark, source_type)
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '财付通')
            """, [tx[0], default_case_id] + list(tx[1:]))

        conn.commit()
        conn.close()

        print(f"\n✓ 迁移完成！")
        print(f"  - 人员: {len(old_persons)} 条")
        print(f"  - 交易: {len(old_transactions)} 条")
        print(f"  - 银行卡: {len(old_bank_cards)} 条")
        print(f"  - 备份文件: {BACKUP_PATH}")
    else:
        print("\n✓ 无旧数据，已创建新数据库结构")


if __name__ == "__main__":
    try:
        migrate()
        print("\n数据库迁移成功！")
    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
