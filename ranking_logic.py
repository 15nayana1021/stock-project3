import sqlite3
import os

# DB 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "stock_game.db")

def update_ranking_snapshot():
    """
    [랭킹 정산 로직]
    12분마다 실행되어 모든 유저의 자산을 계산하고 DB에 저장합니다.
    """
    print("\n⏰ [알림] 12분이 지났습니다! 일일 랭킹 정산을 시작합니다...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. 현재 주가 가져오기
        cursor.execute("SELECT company_name, current_price FROM stocks")
        stock_rows = cursor.fetchall()
        current_prices = {row[0]: row[1] for row in stock_rows}

        # 2. 유저 정보 가져오기
        cursor.execute("SELECT id, username, current_balance FROM users")
        users = cursor.fetchall()
        
        temp_ranking = []

        for user in users:
            user_id, username, cash = user[0], user[1], user[2]
            
            # 주식 자산 계산
            cursor.execute("SELECT company_name, quantity FROM holdings WHERE user_id = ?", (user_id,))
            holdings = cursor.fetchall()
            
            stock_assets = 0
            for holding in holdings:
                name, qty = holding[0], holding[1]
                price = current_prices.get(name, 0)
                stock_assets += price * qty
            
            total_asset = cash + stock_assets
            initial_capital = 1000000
            profit_rate = ((total_asset - initial_capital) / initial_capital) * 100
            
            temp_ranking.append((user_id, username, total_asset, profit_rate))

        # 3. 랭킹 정렬 (자산 많은 순)
        temp_ranking.sort(key=lambda x: x[2], reverse=True)

        # 4. DB 갱신 (기존 랭킹 지우고 새로 쓰기)
        cursor.execute("DELETE FROM ranking_snapshot") # 기존 데이터 삭제
        
        for rank, data in enumerate(temp_ranking):
            cursor.execute("""
                INSERT INTO ranking_snapshot (rank, user_id, username, total_asset, profit_rate)
                VALUES (?, ?, ?, ?, ?)
            """, (rank + 1, data[0], data[1], data[2], round(data[3], 2)))
            
        conn.commit()
        print(f"✅ [완료] 총 {len(temp_ranking)}명의 랭킹이 업데이트되었습니다.")

    except Exception as e:
        print(f"🔥 [오류] 랭킹 업데이트 중 문제 발생: {e}")
    finally:
        conn.close()