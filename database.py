# database.py
import aiosqlite
import asyncio

DB_NAME = "stock_game.db"

async def get_db_connection():
    """FastAPI 라우터에서 쓸 DB 연결 생성기"""
    conn = await aiosqlite.connect(DB_NAME, timeout=30.0)
    conn.row_factory = aiosqlite.Row
    return conn

async def init_db():
    """서버 시작할 때 테이블 싹 다 만드는 함수"""
    async with aiosqlite.connect(DB_NAME, timeout=30.0) as db:
        
        # WAL 모드 활성화 (동시성 문제 해결의 열쇠!)
        await db.execute("PRAGMA journal_mode=WAL;") 
        
        # 1. 유저 테이블 (Users)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            balance INTEGER DEFAULT 1000000,
            level INTEGER DEFAULT 1
        )
        """)

        # 2. 보유 주식 테이블 (Holdings)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            user_id INTEGER,
            company_name TEXT,
            quantity INTEGER,
            average_price REAL,
            PRIMARY KEY (user_id, company_name)
        )
        """)

        # 3. 거래 내역 테이블 (Transactions)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            transaction_type TEXT,
            amount INTEGER,
            balance_after INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 4. 주식 종목 테이블 (Stocks)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            current_price INTEGER,
            description TEXT
        )
        """)

        # 5. 뉴스 테이블 (News)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            impact_level INTEGER, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 6. 퀘스트 목록 (Quests)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS quests (
            quest_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            reward_exp INTEGER
        )
        """)

        # 7. 유저 퀘스트 완료 기록 (UserQuests)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_quests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            quest_name TEXT,
            status TEXT DEFAULT 'COMPLETED',
            reward_amount INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 8. 주문 내역 테이블 (Orders)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            company_name TEXT,
            order_type TEXT,      -- BUY / SELL
            price INTEGER,        -- 희망 가격
            quantity INTEGER,     -- 수량
            status TEXT DEFAULT 'PENDING', -- PENDING / FILLED / CANCELLED
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 9. 초기 데이터 (없으면 삼성전자/SK하이닉스 추가)
        cursor = await db.execute("SELECT count(*) FROM stocks")
        if (await cursor.fetchone())[0] == 0:
            print("⚙️ 초기 주식 데이터 생성 중...")
            await db.execute("INSERT INTO stocks (symbol, company_name, current_price) VALUES (?, ?, ?)", 
                             ("삼성전자", "삼성전자", 70000))
            await db.execute("INSERT INTO stocks (symbol, company_name, current_price) VALUES (?, ?, ?)", 
                             ("SK하이닉스", "SK하이닉스", 120000))
        
        await db.commit()
        print("✅ DB 초기화 및 WAL 모드 설정 완료!")

if __name__ == "__main__":
    asyncio.run(init_db())