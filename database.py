"""
База данных для J.A.R.V.I.S.
Админы хранятся в JSON, остальное в SQLite
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path


class Database:
    """Комбинированная база: админы в JSON, остальное в SQLite"""
    
    def __init__(self, db_path: str = "jarvis.db", admins_file: str = "admins.json"):
        self.db_path = db_path
        self.admins_file = Path(admins_file)
        self.init_db()
        self.init_admins_file()
    
    # ========== JSON ADMINS ==========
    
    def init_admins_file(self):
        """Создать JSON файл для админов если не существует"""
        if not self.admins_file.exists():
            self._save_admins({})
    
    def _load_admins(self) -> Dict:
        """Загрузить админов из JSON"""
        try:
            if self.admins_file.exists():
                with open(self.admins_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Ошибка загрузки админов: {e}")
            return {}
    
    def _save_admins(self, admins: Dict):
        """Сохранить админов в JSON"""
        try:
            with open(self.admins_file, 'w', encoding='utf-8') as f:
                json.dump(admins, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка сохранения админов: {e}")
            return False
    
    # ========== АДМИНЫ (JSON) ==========
    
    def add_admin(self, user_id: int, username: str, added_by: int, is_super: bool = False) -> bool:
        """Добавить администратора в JSON"""
        try:
            admins = self._load_admins()
            admins[str(user_id)] = {
                "user_id": user_id,
                "username": username,
                "added_by": added_by,
                "added_at": datetime.now().isoformat(),
                "is_super_admin": is_super,
                "permissions": {}
            }
            return self._save_admins(admins)
        except Exception as e:
            print(f"Ошибка добавления админа: {e}")
            return False
    
    def remove_admin(self, user_id: int) -> bool:
        """Удалить администратора из JSON"""
        try:
            admins = self._load_admins()
            user_id_str = str(user_id)
            if user_id_str in admins:
                del admins[user_id_str]
                return self._save_admins(admins)
            return False
        except Exception as e:
            print(f"Ошибка удаления админа: {e}")
            return False
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить является ли пользователь админом"""
        admins = self._load_admins()
        return str(user_id) in admins
    
    def is_super_admin(self, user_id: int) -> bool:
        """Проверить является ли супер-админом"""
        admins = self._load_admins()
        admin = admins.get(str(user_id))
        return admin is not None and admin.get("is_super_admin", False)
    
    def get_admins(self) -> List[Dict]:
        """Получить список всех админов"""
        admins = self._load_admins()
        return list(admins.values())
    
    def get_admin_count(self) -> int:
        """Количество админов"""
        return len(self._load_admins())
    
    # ========== SQLITE (пользователи, баны, логи, настройки) ==========
    
    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Инициализация SQLite таблиц (без админов)"""
        with self.get_connection() as conn:
            # Таблица пользователей
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP,
                    message_count INTEGER DEFAULT 0
                )
            """)
            
            # Таблица настроек бота
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица логов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица заблокированных пользователей
            conn.execute("""
                CREATE TABLE IF NOT EXISTS banned (
                    user_id INTEGER PRIMARY KEY,
                    banned_by INTEGER,
                    reason TEXT,
                    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    # ========== ПОЛЬЗОВАТЕЛИ ==========
    
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Добавить или обновить пользователя"""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO users 
                   (user_id, username, first_name, last_name, last_activity)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, first_name, last_name, datetime.now())
            )
            conn.commit()
    
    def update_user_activity(self, user_id: int):
        """Обновить активность пользователя"""
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE users 
                   SET last_activity = ?, message_count = message_count + 1
                   WHERE user_id = ?""",
                (datetime.now(), user_id)
            )
            conn.commit()
    
    def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Получить статистику пользователя"""
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(result) if result else None
    
    def get_all_users(self, limit: int = 100) -> List[Dict]:
        """Получить список пользователей"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM users 
                   ORDER BY last_activity DESC LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_count(self) -> int:
        """Общее количество пользователей"""
        with self.get_connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM users").fetchone()
            return result[0] if result else 0
    
    # ========== НАСТРОЙКИ ==========
    
    def set_setting(self, key: str, value: Any):
        """Установить настройку"""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, json.dumps(value), datetime.now())
            )
            conn.commit()
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Получить настройку"""
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if result:
                try:
                    return json.loads(result[0])
                except:
                    return result[0]
            return default
    
    # ========== БАНЫ ==========
    
    def ban_user(self, user_id: int, banned_by: int, reason: str = ""):
        """Забанить пользователя"""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO banned 
                   (user_id, banned_by, reason, banned_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, banned_by, reason, datetime.now())
            )
            conn.commit()
    
    def unban_user(self, user_id: int) -> bool:
        """Разбанить пользователя"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM banned WHERE user_id = ?", (user_id,))
            conn.commit()
            return conn.total_changes > 0
    
    def is_banned(self, user_id: int) -> bool:
        """Проверить забанен ли пользователь"""
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM banned WHERE user_id = ?", (user_id,)
            ).fetchone()
            return result is not None
    
    def get_banned_users(self) -> List[Dict]:
        """Список забаненных"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT b.*, u.username, u.first_name 
                   FROM banned b
                   LEFT JOIN users u ON b.user_id = u.user_id
                   ORDER BY b.banned_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== ЛОГИ ==========
    
    def log_action(self, user_id: int, action: str, details: str = ""):
        """Залогировать действие"""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT INTO logs (user_id, action, details)
                   VALUES (?, ?, ?)""",
                (user_id, action, details)
            )
            conn.commit()
    
    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        """Получить последние логи"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM logs 
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== СТАТИСТИКА ==========
    
    def get_stats(self) -> Dict:
        """Получить полную статистику"""
        with self.get_connection() as conn:
            stats = {
                "total_users": self.get_user_count(),
                "total_admins": self.get_admin_count(),
                "banned_users": conn.execute(
                    "SELECT COUNT(*) FROM banned"
                ).fetchone()[0],
                "today_active": conn.execute(
                    """SELECT COUNT(*) FROM users 
                       WHERE date(last_activity) = date('now')"""
                ).fetchone()[0],
                "week_active": conn.execute(
                    """SELECT COUNT(*) FROM users 
                       WHERE last_activity >= datetime('now', '-7 days')"""
                ).fetchone()[0],
            }
            return stats


# Глобальный экземпляр
db = Database()
