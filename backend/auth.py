"""
用户认证模块
"""
import aiosqlite
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import os

# JWT 配置
SECRET_KEY = os.getenv("SECRET_KEY", "fapiao_secret_key_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天

# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthManager:
    """认证管理器"""

    def __init__(self, db_path: str = "data/users.db"):
        self.db_path = db_path

    async def init_db(self):
        """初始化数据库，创建用户表"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

            # 创建默认管理员账号（如果不存在）
            await db.execute("""
                INSERT OR IGNORE INTO users (username, hashed_password)
                VALUES (?, ?)
            """, ("admin", ""))  # 默认密码为空
            await db.commit()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        if not hashed_password:
            # 默认空密码
            return plain_password == ""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """获取密码哈希"""
        if not password:
            return ""  # 允许空密码
        return pwd_context.hash(password)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    async def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        """验证用户"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            user = await cursor.fetchone()
            if not user:
                return None
            if not self.verify_password(password, user["hashed_password"]):
                return None
            return {
                "id": user["id"],
                "username": user["username"]
            }

    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改密码"""
        async with aiosqlite.connect(self.db_path) as db:
            # 先验证旧密码
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            user = await cursor.fetchone()
            if not user:
                return False
            if not self.verify_password(old_password, user["hashed_password"]):
                return False

            # 更新密码
            hashed_password = self.get_password_hash(new_password)
            await db.execute(
                "UPDATE users SET hashed_password = ? WHERE username = ?",
                (hashed_password, username)
            )
            await db.commit()
            return True


# 全局认证管理器实例
auth_manager = AuthManager()
