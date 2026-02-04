import aiosqlite
import os
from typing import AsyncGenerator

# 1. 경로 설정: 상위 폴더의 stock_game.db를 가리킴
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "stock_game.db")

# 2. API용 공통 DB 연결 함수
async def get_db_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

# 3. 트레이딩 시스템 테이블 초기화 함수
async def init_trade_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        # 유저 지갑
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                current_balance REAL DEFAULT 1000000
            )
        """)
        # 주식 보유 현황
        await db.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                company_name TEXT,
                quantity INTEGER DEFAULT 0,
                average_price REAL DEFAULT 0,
                UNIQUE(user_id, company_name)
            )
        """)
        # 거래 내역 (원장)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_type TEXT,
                amount REAL,
                balance_after REAL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 4. 미체결 주문 관리 테이블 (주문장)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                company_name TEXT,
                order_type TEXT, -- 'BUY'(매수) 또는 'SELL'(매도)
                price REAL,      -- 사용자가 원하는 지정가
                quantity INTEGER,
                status TEXT DEFAULT 'PENDING', -- 'PENDING'(대기), 'FILLED'(체결), 'CANCELLED'(취소)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
