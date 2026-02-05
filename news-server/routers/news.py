from fastapi import APIRouter, HTTPException, Query, Path, Depends, Header
import aiosqlite
from typing import List, Dict, Any
from database import get_db_connection
from pydantic import BaseModel
from services.gamification import gain_exp, check_quest 

router = APIRouter(prefix="/api/news", tags=["News"])

# (응답 모델은 필요하면 사용, 지금은 dict로 반환해도 됨)
class NewsResponse(BaseModel):
    id: int
    company_name: str
    title: str
    summary: str
    impact_score: int
    reason: str
    created_at: str

# 1. 뉴스 목록 조회 (수정 없음, 경험치 지급 X)
@router.get("/", response_model=List[Dict[str, Any]])
async def get_published_news(
    limit: int = Query(20, description="가져올 최신 뉴스 개수"),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """
    [뉴스 목록 조회]
    - 여기서는 경험치를 주지 않습니다. (제목만 봤으니까요)
    """
    try:
        query = """
            SELECT id, company_name, title, summary, impact_score, reason, created_at
            FROM news_pool
            -- WHERE is_published = 1  <-- 나중에 주석 해제
            ORDER BY created_at DESC
            LIMIT ?
        """
        async with db.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")


# 2. 뉴스 상세 조회
@router.get("/{news_id}")
async def get_news_detail(
    news_id: int = Path(..., description="읽으려는 뉴스의 ID"),
    x_user_id: int = Header(1, alias="X-User-ID", description="테스트용 유저 ID"),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """
    [뉴스 상세 읽기]
    헤더에 'X-User-ID'를 넣으면 해당 유저가 경험치를 받습니다.
    (기본값: 1번 유저)
    
    * 게이미피케이션 적용:
      - 경험치 10 지급 (단, 레벨 5 이상은 지급 안 함)
      - 뉴스 읽기 퀘스트 체크
    """
    # 1. 뉴스 데이터 가져오기
    query = "SELECT * FROM news_pool WHERE id = ?"
    async with db.execute(query, (news_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="뉴스를 찾을 수 없습니다.")
        news_item = dict(row)

    # 2. 경험치 지급 대상 설정 (헤더에서 받은 유저 ID 사용)
    target_user_id = x_user_id

    # 3. 게이미피케이션 로직 실행
    await gain_exp(target_user_id, 10, max_level=5)
    
    # 퀘스트 체크 (레벨 상관없이 퀘스트는 깰 수 있게 둠)
    await check_quest(target_user_id, "news_read_1")

    return news_item