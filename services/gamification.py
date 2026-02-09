from datetime import datetime
import aiosqlite
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "stock_game.db")

# 레벨업에 필요한 경험치 테이블 (예: 1->2 가는데 100 필요)
LEVEL_TABLE = {
    1: 100,
    2: 300,
    3: 600,
    4: 1000,
    5: 1500  # Lv.5 달성 목표
}

#max_level 파라미터 추가
async def gain_exp(user_id: int, amount: int, max_level: int = None):
    """
    유저에게 경험치를 지급하고, 레벨업 조건을 체크합니다.
    max_level이 설정된 경우, 해당 레벨 이상이면 경험치를 지급하지 않습니다.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. 현재 정보 가져오기
        cursor = await db.execute("SELECT level, exp FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if not row:
            return # 유저 없으면 종료
        
        current_level, current_exp = row

        # (현재 레벨을 확인한 직후, 경험치를 더하기 전에 검사합니다)
        if max_level is not None and current_level >= max_level:
            print(f"🚫 레벨 {current_level}이라서 더 이상 이 행동으로 경험치를 얻을 수 없습니다. (제한: LV.{max_level})")
            return

        # 2. 경험치 지급
        new_exp = current_exp + amount
        new_level = current_level
        
        # 3. 레벨업 체크 (반복문으로 한 번에 여러 레벨업 가능하게)
        while True:
            required_exp = LEVEL_TABLE.get(new_level, 999999) # 만렙이면 무한대
            if new_exp >= required_exp:
                new_exp -= required_exp
                new_level += 1
                print(f"🎉 유저 {user_id}님이 레벨 {new_level}로 성장했습니다!")
            else:
                break
        
        # 4. DB 업데이트
        await db.execute("UPDATE users SET level = ?, exp = ? WHERE id = ?", (new_level, new_exp, user_id))
        await db.commit()
        
        return {"level": new_level, "exp": new_exp, "leveled_up": new_level > current_level}

# check_quest 함수는 기존과 동일하게 유지
async def check_quest(user_id: int, quest_id: str):
    """
    퀘스트 완료 처리 (단순 완료형)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # 이미 깼는지 확인
        cursor = await db.execute("SELECT is_completed FROM user_quests WHERE user_id = ? AND quest_id = ?", (user_id, quest_id))
        row = await cursor.fetchone()
        
        if row and row[0]: # 이미 깸
            return False 

        # 퀘스트 정보 가져오기 (보상 확인)
        cursor = await db.execute("SELECT reward_exp FROM quests WHERE quest_id = ?", (quest_id,))
        quest_data = await cursor.fetchone()
        if not quest_data:
            return False

        reward = quest_data[0]
        
        # 완료 처리
        await db.execute("""
            INSERT OR REPLACE INTO user_quests (user_id, quest_id, is_completed, completed_at)
            VALUES (?, ?, 1, ?)
        """, (user_id, quest_id, datetime.now()))
        
        await db.commit()
        print(f"🏆 퀘스트 완료! [{quest_id}] 보상: {reward} EXP")
        
        # 보상 지급 (위에서 만든 함수 재사용)
        await gain_exp(user_id, reward)
        
        return True