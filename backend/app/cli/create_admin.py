"""交互式创建首个管理员。"""

import asyncio
from getpass import getpass

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import create_engine, create_session_factory
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services.users import create_user


def read_admin_data() -> UserCreate:
    """从终端读取管理员资料，密码不会回显。"""
    return UserCreate(
        email=input("请输入管理员邮箱: ").strip().lower(),
        full_name=input("请输入管理员姓名: ").strip(),
        password=getpass("请输入管理员密码: "),
        role=Role.ADMIN,
    )


async def main() -> int:
    """读取配置并通过统一 Service 创建管理员。"""
    try:
        data = read_admin_data()
    except ValidationError:
        print("创建失败: 输入数据不符合要求")
        return 1

    database_url = Settings().database_url
    if database_url is None:
        print("创建失败: DATABASE_URL 未配置")
        return 1

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            user = await create_user(session, data)
    except AppError as exc:
        print(f"创建失败: {exc}")
        return 1
    except Exception:
        print("创建失败: 发生内部错误")
        return 1
    finally:
        await engine.dispose()

    print(f"管理员 {user.email} 创建成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
