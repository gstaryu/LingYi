import sqlite3
import json
import os

# 使用绝对路径，确保在任何执行环境下都能准确找到 storage 文件夹
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "storage", "patient_profiles.db")

class ProfileManager:
    def __init__(self):
        # 显式确保 storage 目录存在
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            # check_same_thread=False 兼容多线程环境（如 Streamlit）
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS profiles (
                        patient_id TEXT PRIMARY KEY,
                        constitution TEXT,
                        allergies TEXT,
                        past_history TEXT,
                        last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS threads (
                        thread_id TEXT PRIMARY KEY,
                        username TEXT,
                        title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Try to add title column to existing table (ignores error if it already exists)
                try:
                    conn.execute("ALTER TABLE threads ADD COLUMN title TEXT")
                except:
                    pass
                conn.commit()
                # 显式写一条日志确认文件创建
                print(f"🗄️ 数据库连接成功: {DB_PATH}")
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")

    def get_profile(self, patient_id: str) -> dict:
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM profiles WHERE patient_id = ?", (patient_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "constitution": row["constitution"],
                        "allergies": row["allergies"],
                        "past_history": json.loads(row["past_history"]) if row["past_history"] else []
                    }
        except Exception as e:
            print(f"❌ 读取画像失败: {e}")
        return {"constitution": "未知", "allergies": "无", "past_history": []}

    def update_profile(self, patient_id: str, data: dict):
        current = self.get_profile(patient_id)
        new_history = current.get("past_history", [])
        if data.get("new_record"):
            new_history.append(data["new_record"])
            new_history = new_history[-10:]

        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.execute("""
                    INSERT INTO profiles (patient_id, constitution, allergies, past_history, last_update)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        constitution = excluded.constitution,
                        allergies = excluded.allergies,
                        past_history = excluded.past_history,
                        last_update = CURRENT_TIMESTAMP
                """, (
                    patient_id,
                    data.get("constitution", current["constitution"]),
                    data.get("allergies", current["allergies"]),
                    json.dumps(new_history, ensure_ascii=False)
                ))
                conn.commit()
                print(f"✅ 画像已持久化存储: {patient_id}")
        except Exception as e:
            print(f"❌ 更新画像失败: {e}")

    def list_profiles(self) -> list:
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.row_factory = sqlite3.Row
                # 获取所有不重复的患者对历史
                cursor = conn.execute("SELECT patient_id, last_update FROM profiles ORDER BY last_update DESC")
                return [{"patient_id": r["patient_id"], "last_update": r["last_update"]} for r in cursor.fetchall()]
        except Exception as e:
            print(f"❌ 获取就诊列表失败: {e}")
            return []

    def get_threads(self, username: str) -> list:
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT thread_id, title, created_at FROM threads WHERE username = ? ORDER BY created_at DESC", (username,))
                return [{"thread_id": r["thread_id"], "title": r["title"], "created_at": r["created_at"]} for r in cursor.fetchall()]
        except Exception as e:
            return []

    def verify_user(self, username: str, password: str) -> bool:
        """验证用户密码。"""
        import hashlib
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
                row = cursor.fetchone()
                if row:
                    return row["password"] == pwd_hash
        except Exception as e:
            print(f"❌ 用户验证失败: {e}")
        return False

    def create_user(self, username: str, password: str) -> bool:
        """创建新用户。如果存在返回 False。"""
        import hashlib
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                cursor = conn.execute("SELECT username FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    return False
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, pwd_hash))
                conn.commit()
                return True
        except Exception as e:
            print(f"❌ 用户创建失败: {e}")
            return False

    def add_thread(self, username: str, thread_id: str):
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.execute("INSERT OR IGNORE INTO threads (thread_id, username) VALUES (?, ?)", (thread_id, username))
                conn.commit()
        except:
            pass

    def rename_thread(self, thread_id: str, new_title: str):
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.execute("UPDATE threads SET title = ? WHERE thread_id = ?", (new_title, thread_id))
                conn.commit()
        except Exception as e:
            print(f"❌ Renaming thread failed: {e}")

    def delete_thread(self, thread_id: str):
        try:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
                conn.commit()
        except:
            pass

profile_manager = ProfileManager()