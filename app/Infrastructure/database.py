from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base, Session

from conf import settings

"""
todo: 공통된 session 사용시 AsyncSession 에서 refresh 를 하여 업데이트된 데이터를 갱신하는데,
      잘 되지 않아 Context Manager 로 DB 접근시 새로운 세션을 생성하여 사용.
      공통된 session 에서 refresh 정확히 사용하는 방법 찾아야함.

      1. 매번 커넥션을 하는게 맞을지?: 매번드는 커넥션 비용(리소스)
      2. 아니면 커넥션을 계속 유지하고 있는게 맞을지?: 커넥션 풀을 사용 + 커밋 될때마다 데이터 갱신(refresh)
"""


Base = declarative_base()
async_engine = create_async_engine(
    f'mysql+aiomysql://{settings.config.USERNAME}:{settings.config.PASSWORD}'
    f'@{settings.config.HOST}:{settings.config.PORT}/{settings.config.DATABASE}',
    echo=True if settings.config.ENV != settings.EmojiRankEnv.PROD.value else False,
    future=True
)
engine = create_engine(
    f'mysql+pymysql://{settings.config.USERNAME}:{settings.config.PASSWORD}'
    f'@{settings.config.HOST}:{settings.config.PORT}/{settings.config.DATABASE}',
    echo=True if settings.config.ENV != settings.EmojiRankEnv.PROD.value else False,
    # connect_args={"check_same_thread": False}
)


class MysqlConnectionManager:
    _client = None

    @classmethod
    def get_connection(cls, is_async: bool):
        if cls._client is None:
            if is_async:
                # todo: asyncio scoped session 가 필요한가?
                # https://docs.sqlalchemy.org/en/14/orm/extensions/asyncio.html#using-asyncio-scoped-session
                # 비동기로 db connection 을 처리하려면 scoped_session 을 사용하면 안된다.
                # 참고: https://blog.neonkid.xyz/266
                cls._client = AsyncSession(bind=async_engine, expire_on_commit=False)
            else:
                cls._client = scoped_session(sessionmaker(
                    autocommit=False, autoflush=False, bind=engine, class_=Session
                ))

        return cls._client


@asynccontextmanager
async def async_session_manager() -> AsyncSession:
    session = AsyncSession(bind=async_engine, expire_on_commit=True)

    try:
        yield session
        await session.commit()
    except Exception as err:
        await session.rollback()
        print(err)
    finally:
        await session.close()
        # await async_engine.dispose()
