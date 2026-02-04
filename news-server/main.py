from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from database import init_trade_tables  # 테이블 초기화 함수 임포트
from routers import news, trade, rank   # trade, rank 라우터 추가
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from ranking_logic import update_ranking_snapshot

# 스케줄러 설정
scheduler = BackgroundScheduler()
scheduler.add_job(update_ranking_snapshot, 'interval', minutes=12)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- [시작] 서버가 켜질 때 실행되는 구간 ---
    print("🚀 서버 가동! 테이블 생성 및 스케줄러를 시작합니다...")
    
    # 1. DB 테이블 먼저 생성 (순서 중요!)
    await init_trade_tables()
    
    # 2. 스케줄러 시작
    scheduler.start()
    
    # 3. 켜지자마자 랭킹 1회 업데이트 (확인용)
    print("⚡ 초기 랭킹 데이터 생성 중...")
    update_ranking_snapshot()
    
    yield
    
    # --- [종료] 서버가 꺼질 때 실행되는 구간 ---
    print("🛑 서버 종료! 스케줄러를 끕니다.")
    scheduler.shutdown()

app = FastAPI(
    title="Money Quest News API",
    description="React Native 연동을 위한 독립형 뉴스 서버",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(news.router)
app.include_router(trade.router)
app.include_router(rank.router)

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "News Server is running! 🚀"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)