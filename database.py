import sqlite3

def init_db():
    # stock_game.db 파일 생성 및 연결
    conn = sqlite3.connect('stock_game.db')
    cursor = conn.cursor()

    # 뉴스 저장용 테이블 생성
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            impact_score INTEGER,
            reason TEXT,
            is_published INTEGER DEFAULT 0, -- 0: 대기, 1: 공개됨
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("--- [Money Quest] 데이터베이스 초기화 완료 ---")

if __name__ == "__main__":
    init_db()