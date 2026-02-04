from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NewsResponse(BaseModel):
    """
    뉴스 API 응답 모델
    DB의 컬럼과 1:1로 매핑되어 API 문서(Swagger)를 자동 생성합니다.
    """
    id: int
    company_name: str
    title: str
    summary: Optional[str] = None
    impact_score: Optional[int] = None
    reason: Optional[str] = None
    created_at: str  # SQLite의 datetime은 문자열로 반환됨

    class Config:
        # DB row(딕셔너리 형태)를 Pydantic 모델로 자동 변환 허용
        from_attributes = True