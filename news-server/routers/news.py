from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
import aiosqlite
from database import get_db_connection
from schemas import NewsResponse

# 라우터 선언 (나중에 메인 앱에 이 라우터만 등록하면 끝!)
router = APIRouter(
    prefix="/api/news",
    tags=["News System 📰"]
)

@router.get("/", response_model=List[NewsResponse])
async def get_published_news(
    limit: int = Query(20, description="가져올 최신 뉴스 개수"),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """
    [공개된 뉴스 조회]
    - 시뮬레이터에 의해 'is_published=1'로 설정된 뉴스만 가져옵니다.
    - 최신순으로 정렬하여 반환합니다.
    """
    try:
        query = """
            SELECT id, company_name, title, summary, impact_score, reason, created_at
            FROM news_pool
            --WHERE is_published = 1
            ORDER BY created_at DESC
            LIMIT ?
        """
        async with db.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            
            # Pydantic 모델 리스트로 변환하여 반환
            return [dict(row) for row in rows]
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")