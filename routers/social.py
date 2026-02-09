from fastapi import APIRouter, HTTPException
from database import get_db_connection

router = APIRouter()

# 🏆 [랭킹 시스템] 부자 순위 TOP 10 조회
@router.get("/ranking")
async def get_ranking():
    conn = await get_db_connection()
    try:
        # 돈(balance)이 많은 순서대로 10명만 가져오기
        async with conn.execute("""
            SELECT username, level, balance 
            FROM users 
            ORDER BY balance DESC 
            LIMIT 10
        """) as cursor:
            rankers = await cursor.fetchall()
        
        return [
            {
                "rank": i + 1,
                "username": row['username'],
                "level": row['level'],
                "balance": row['balance']
            }
            for i, row in enumerate(rankers)
        ]
    finally:
        await conn.close()

# 👤 [내 정보] 레벨 및 경험치 조회
@router.get("/my-profile/{user_id}")
async def get_my_profile(user_id: int):
    conn = await get_db_connection()
    try:
        # 1. 내 정보 가져오기
        async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        # 2. 완료한 퀘스트 개수 세기 (업적 점수용)
        async with conn.execute("SELECT count(*) FROM user_quests WHERE user_id = ?", (user_id,)) as cursor:
            quest_count = (await cursor.fetchone())[0]

        return {
            "username": user['username'],
            "level": user['level'],
            "balance": user['balance'],
            "quest_cleared": quest_count,  # 퀘스트 깬 횟수
            "next_level_exp": user['level'] * 1000  # (예시) 다음 레벨까지 필요한 경험치
        }
    finally:
        await conn.close()