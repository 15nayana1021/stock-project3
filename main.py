# main.py (Real Engine Version)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import random
from datetime import datetime
import aiosqlite


# 엔진과 모델 임포트

from database import init_db
from routers import trade, social
from market_engine import MarketEngine  # 진짜 엔진
from domain_models import Order, OrderType, OrderSide, Agent # 주문 모델


# [전역 설정]
TARGET_TICKERS = ["삼성전자", "소현컴퍼니", "상은테크놀로지", "예진캐피탈"]

# 엔진 초기화
engine = MarketEngine()

# 초기 데이터 (전역 변수 - 종목별 관리)
current_news_display = "장 시작 준비 중..."
price_history = {ticker: [] for ticker in TARGET_TICKERS}
current_mentor_comments = {ticker: [] for ticker in TARGET_TICKERS}


# [시뮬레이션 엔진] - 봇 활동 + 사용자 주문 체결 처리(청산)
async def simulate_market_background():
    global current_news_display, price_history, current_mentor_comments
    
    print("🚀 리얼 마켓 엔진 & 청산 시스템 가동!")
    
    # [Step 0] 멘토단 결성
    real_ai_mode = False 
    try:
        from mentor_personas import MENTOR_PROFILES
        real_ai_mode = True 
        print(f"✅ Real AI 모드 활성화!")
    except Exception as e:
        print(f"⚠️ [경고] AI 설정 실패: {e}")

    loop_count = 0
    
    # DB 연결 (WAL 모드)
    db = await aiosqlite.connect("stock_game.db", timeout=30.0)
    await db.execute("PRAGMA journal_mode=WAL;") 
    db.row_factory = aiosqlite.Row 

    try:
        
        # [초기화] 사용자 종목 등록
        for ticker in TARGET_TICKERS:
            # DB 가격 동기화
            cursor = await db.execute("SELECT * FROM stocks WHERE company_name = ?", (ticker,))
            row = await cursor.fetchone()
            start_price = row['current_price'] if row else 70000
            
            if not row:
                await db.execute("INSERT OR IGNORE INTO stocks (symbol, company_name, current_price) VALUES (?, ?, ?)", 
                                 (ticker, ticker, start_price))
            
            # 엔진 등록
            if ticker not in engine.companies:
                from domain_models import Company
                new_comp = Company(ticker=ticker, name=ticker, sector="Tech", description="Custom", current_price=float(start_price), total_shares=1000000)
                engine.companies[ticker] = new_comp
                engine.order_books[ticker] = {"BUY": [], "SELL": []}
                print(f"⚙️ 엔진 등록: {ticker}")

        await db.commit()

        # [무한 루프] 봇 주문 + 사용자 체결 확인
        while True:
            await asyncio.sleep(1) 
            loop_count += 1
            
            # 뉴스 로테이션
            if loop_count % 10 == 0:
                events = ["반도체 수요 폭발", "금리 동결 발표", "경쟁사 실적 부진", "특별한 이슈 없음", "신제품 출시 임박"]
                current_news_display = random.choice(events)

            for ticker in TARGET_TICKERS:
                if ticker not in engine.companies: continue
                
                # 1. 봇(Bot)의 랜덤 주문 투입
                current_p = engine.companies[ticker].current_price
                bot_side = random.choice([OrderSide.BUY, OrderSide.SELL])
                spread = random.randint(-500, 500)
                order_price = int(current_p + spread)
                if order_price < 10: order_price = 10
                qty = random.randint(1, 5) # 봇은 소량으로 자주 거래

                bot_order = Order(
                    agent_id="Bot_Noise", ticker=ticker, side=bot_side,
                    order_type=OrderType.LIMIT, quantity=qty, price=order_price
                )
                engine.place_order(bot_order)
                
                # 2. 가격 변동 DB 반영
                new_price = int(engine.companies[ticker].current_price)
                if new_price != current_p:
                    await db.execute("UPDATE stocks SET current_price = ? WHERE company_name = ?", (new_price, ticker))
                    await db.commit()
                    # 봇 체결 알림 (너무 많으면 주석 처리)
                    # print(f"✨ [시장] {ticker} 현재가 {new_price}원으로 변경")

                # 히스토리 저장
                price_history[ticker].append({"time": datetime.now().strftime("%H:%M:%S"), "price": new_price})
                if len(price_history[ticker]) > 30: price_history[ticker].pop(0)

                # 3. 멘토링 (삼성전자만 Real AI)
                if real_ai_mode and ticker == "삼성전자" and (loop_count % 30 == 0):
                    # ... (AI 로직 생략: 기존 코드 유지) ...
                    # (너무 길어지니 위에서 작성하신 AI 코드가 그대로 있다고 가정합니다)
                    pass 
                elif (loop_count % 5 == 0):
                    # 무료 멘트
                    comments_pool = [{"n": "시스템", "c": "거래량 분석 중...", "s": "value-box"}, {"n": "알림", "c": "변동성 확대 주의", "s": "momentum-box"}]
                    if ticker != "삼성전자" or not current_mentor_comments[ticker]:
                        current_mentor_comments[ticker] = random.sample(comments_pool, 1)

            
            # 사용자 주문 정산 (Settlement)
            # DB에 'PENDING'으로 남아있는 주문들을 가져와서, 엔진에서 사라졌는지(체결됐는지) 확인합니다.         
            async with db.execute("SELECT * FROM orders WHERE status = 'PENDING'") as cursor:
                pending_orders = await cursor.fetchall()

            for db_order in pending_orders:
                order_id = db_order['id']
                user_id = db_order['user_id']
                target_ticker = db_order['company_name']
                o_type = db_order['order_type'] # 'BUY' or 'SELL'
                qty = db_order['quantity']
                price = db_order['price']
                
                # 엔진에서 내 주문 찾기 (Agent ID: User_{user_id})
                # 엔진의 오더북(호가창)을 뒤져서 내 주문이 남아있는지 봅니다.
                is_alive_in_engine = False
                book = engine.order_books.get(target_ticker, {"BUY": [], "SELL": []})
                
                # 매수 주문이면 BUY 쪽, 매도면 SELL 쪽 확인
                check_list = book["BUY"] if o_type == "BUY" else book["SELL"]
                
                for eng_order in check_list:
                    if eng_order.agent_id == f"User_{user_id}" and eng_order.price == price:
                        # 아직 호가창에 남아있음 -> 체결 안 됨
                        is_alive_in_engine = True
                        break
                
                # 😲 호가창에서 사라졌다? = 체결 완료 (FILLED)!
                if not is_alive_in_engine:
                    print(f"🎉 [체결 성공] 사용자 {user_id}님의 {target_ticker} 주문이 체결되었습니다!")
                    
                    # 1. 주문 상태 변경
                    await db.execute("UPDATE orders SET status = 'FILLED' WHERE id = ?", (order_id,))
                    
                    # 2. 자산 지급 (Step 3에서 이미 차감했으므로, 들어올 것만 주면 됨)
                    if o_type == "BUY":
                        # 매수 성공: 주식 지급
                        await db.execute("""
                            INSERT INTO holdings (user_id, company_name, quantity, average_price)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(user_id, company_name) DO UPDATE SET quantity = quantity + ?, average_price = ?
                        """, (user_id, target_ticker, qty, price, qty, price)) # 평단가는 단순하게 체결가로 갱신
                        
                    elif o_type == "SELL":
                        # 매도 성공: 현금 지급
                        income = price * qty
                        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (income, user_id))

                    # 3. 퀘스트 자동 달성 (보너스)
                    quest_name = "첫 매수 성공" if o_type == "BUY" else "첫 매도 성공"
                    cursor = await db.execute("SELECT count(*) FROM user_quests WHERE user_id = ? AND quest_name = ?", (user_id, quest_name))
                    if (await cursor.fetchone())[0] == 0:
                         reward = 500000 if o_type == "BUY" else 1000000
                         await db.execute("INSERT INTO user_quests (user_id, quest_name, reward_amount) VALUES (?, ?, ?)", (user_id, quest_name, reward))
                         await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (reward, user_id))
                         print(f"🎁 [퀘스트 완료] {quest_name}! 보상 {reward}원 지급")

                    await db.commit() # 정산 확정

    except Exception as e:
        print(f"❌ 시뮬레이션 치명적 에러: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()

# [FastAPI 앱 설정]
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(simulate_market_background())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(trade.router)
app.include_router(social.router, prefix="/api/social", tags=["Social & Ranking"])

@app.get("/api/market-data")
async def get_market_data(ticker: str = "삼성전자"):
    if ticker not in engine.companies:
        return {"ticker": ticker, "price": 0, "error": "존재하지 않는 종목"}

    comp = engine.companies[ticker]
    book = engine.order_books.get(ticker, {"BUY": [], "SELL": []})
    
    # 엔진 호가
    # engine.order_books에 있는 Order 객체들을 딕셔너리로 변환
    buy_orders = [o.dict() for o in book["BUY"][:5]]  # 상위 5개
    sell_orders = [o.dict() for o in book["SELL"][:5]] # 상위 5개

    return {
        "ticker": ticker,     
        "name": ticker,
        "price": comp.current_price,
        "news": current_news_display,
        "history": price_history.get(ticker, []),
        "buy_orders": buy_orders,
        "sell_orders": sell_orders,
        "mentors": current_mentor_comments.get(ticker, [])
    }

app.mount("/", StaticFiles(directory="static", html=True), name="static")