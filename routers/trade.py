from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import aiosqlite
from database import get_db_connection
from services.gamification import gain_exp, check_quest
from domain_models import Order, OrderType, OrderSide

router = APIRouter(prefix="/api/trade", tags=["Trade"])


# 1. 데이터 모델 (Schema)
class UserCreate(BaseModel):
    username: str

class TradeRequest(BaseModel):
    user_id: int
    company_name: str
    price: float  # 1주당 현재 가격
    quantity: int # 사고 팔 개수 (매수는 양수)

# 2. 지갑 생성 및 초기 자금 지급 API (가입)
@router.post("/user/init")
async def init_user(user: UserCreate, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [안전 호환 모드] 유저 생성 및 초기 자금 지급
    """
    try:
        # 1. 유저 생성 (INSERT 실행)
        cursor = await db.execute(
            "INSERT INTO users (username, balance) VALUES (?, 1000000)", 
            (user.username,)
        )
        await db.commit()  # 저장을 먼저 해야 ID가 생깁니다.
        
        # 2. 방금 만든 유저의 ID 확인 (RETURNING 대신 lastrowid 사용)
        user_id = cursor.lastrowid
        balance = 1000000.0
        
        # 3. 원장(Ledger)에 가입 축하금 기록
        await db.execute("""
            INSERT INTO transactions (user_id, transaction_type, amount, balance_after, description)
            VALUES (?, 'DEPOSIT', 1000000, 1000000, '신규 가입 축하금')
        """, (user_id,))
        
        await db.commit() # 최종 저장
        
        return {
            "status": "created", 
            "user_id": user_id,
            "balance": balance, 
            "message": f"환영합니다, {user.username}님! 지갑 생성 완료! (100만원 지급)"
        }
        
    except aiosqlite.IntegrityError:
        # 이미 존재하는 아이디인 경우
        cursor = await db.execute("SELECT id, balance FROM users WHERE username = ?", (user.username,))
        row = await cursor.fetchone()
        return {
            "status": "exists", 
            "user_id": row[0], 
            "balance": row[1], 
            "message": f"이미 계정이 있습니다. 환영합니다, {user.username}님!"
        }


# 3. 주식 매수 API (Transaction)
@router.post("/buy")
async def buy_stock(trade: TradeRequest, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [매수 트랜잭션]
    1. 잔액 확인 (balance) -> 2. 잔액 차감 -> 3. 주식 지급 -> 4. 경험치/퀘스트
    """
    total_cost = trade.price * trade.quantity
    
    try:
        # 🔒 트랜잭션 시작
        await db.execute("BEGIN IMMEDIATE") 
        
        # 1. 잔액 확인
        cursor = await db.execute("SELECT balance FROM users WHERE id = ?", (trade.user_id,))
        row = await cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        
        balance_amount = row[0]
        
        if balance_amount < total_cost:
            raise HTTPException(status_code=400, detail="잔액이 부족합니다.")

        # 2. 잔액 차감
        new_balance = balance_amount - total_cost
        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, trade.user_id))

        # 3. 주식 보유량 업데이트
        cursor = await db.execute("SELECT quantity, average_price FROM holdings WHERE user_id = ? AND company_name = ?", (trade.user_id, trade.company_name))
        holding = await cursor.fetchone()
        
        if holding:
            # 추가 매수
            old_qty, old_avg = holding
            new_qty = old_qty + trade.quantity
            new_avg = ((old_qty * old_avg) + total_cost) / new_qty
            await db.execute("UPDATE holdings SET quantity = ?, average_price = ? WHERE user_id = ? AND company_name = ?", (new_qty, new_avg, trade.user_id, trade.company_name))
        else:
            # 신규 매수
            await db.execute("INSERT INTO holdings (user_id, company_name, quantity, average_price) VALUES (?, ?, ?, ?)", (trade.user_id, trade.company_name, trade.quantity, trade.price))

        await db.commit()
        try:
            # 1. 경험치 지급 (20점, 레벨 제한 없음)
            #await gain_exp(trade.user_id, 20)
            
            # 2. '첫 주식 매수' 퀘스트 체크
            await check_quest(trade.user_id, "trade_first")
        except Exception as e:
            # 보상 지급 중 에러가 나도, 주식 산 건 취소되면 안 되니까 로그만 찍고 넘어감
            print(f"⚠️ 보상 지급 중 에러 발생: {e}")

        return {"message": "매수 체결 완료!", "balance": new_balance}

    except Exception as e:
        await db.rollback() # 에러 나면 주식 사기 전으로 되돌림
        raise e

        # 4. 거래 원장(Ledger) 기록
        await db.execute("""
            INSERT INTO transactions (user_id, transaction_type, amount, balance_after, description)
            VALUES (?, 'BUY', ?, ?, ?)
        """, (trade.user_id, -total_cost, new_balance, f"{trade.company_name} {trade.quantity}주 매수"))
        
        # ✅ 승인 (Commit)
        await db.commit()
        
        return {
            "status": "success", 
            "message": f"{trade.company_name} 매수 성공!", 
            "balance": new_balance,
            "holdings": {"company": trade.company_name, "quantity": trade.quantity}
        }

    except Exception as e:
        # ❌ 에러 발생 시 취소 (Rollback)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"거래 실패: {str(e)}")

# 4. 내 정보(잔액) 조회 API
@router.get("/user/{user_id}")
async def get_user_info(user_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [지갑 조회]
    앱 메인화면에 띄워줄 유저의 현재 잔액과 보유 주식 정보를 가져옵니다.
    """
    # 1. 잔액 조회
    cursor = await db.execute("SELECT username, balance FROM users WHERE id = ?", (user_id,))
    user_row = await cursor.fetchone()
    
    if not user_row:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        
    # 2. 보유 주식 조회 (현재 가지고 있는 것만)
    cursor = await db.execute("""
        SELECT company_name, quantity, average_price 
        FROM holdings 
        WHERE user_id = ? AND quantity > 0
    """, (user_id,))
    holdings_rows = await cursor.fetchall()
    
    return {
        "username": user_row[0],
        "balance": user_row[1],
        "holdings": [dict(row) for row in holdings_rows]
    }

# 5. 보상 지급 API (퀘스트, 배당금 등)
# 보상 요청 데이터 모델
class RewardRequest(BaseModel):
    user_id: int
    amount: float   # 받을 금액 (예: 50000)
    description: str # 보상 이유 (예: "일일 퀘스트 완료", "출석 보상")

@router.post("/reward")
async def give_reward(reward: RewardRequest, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [보상 지급 시스템]
    - 특정 유저에게 돈을 지급합니다.
    - 퀘스트 완료, 레벨업 축하금, 배당금 지급 등에 사용됩니다.
    - 거래 장부(Ledger)에 'REWARD' 타입으로 기록됩니다.
    """
    try:
        await db.execute("BEGIN IMMEDIATE") # 트랜잭션 시작

        # 1. 유저 존재 확인 및 현재 잔액 조회
        cursor = await db.execute("SELECT balance FROM users WHERE id = ?", (reward.user_id,))
        row = await cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
            
        balance = row[0]
        
        # 2. 잔액 증가 (더하기)
        new_balance = balance + reward.amount
        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, reward.user_id))

        # 3. 거래 원장(Ledger)에 기록 (돈의 출처 남기기)
        await db.execute("""
            INSERT INTO transactions (user_id, transaction_type, amount, balance_after, description)
            VALUES (?, 'REWARD', ?, ?, ?)
        """, (reward.user_id, reward.amount, new_balance, reward.description))

        await db.commit() # 저장

        return {
            "status": "success",
            "message": f"보상 지급 완료: {reward.amount}원",
            "balance": new_balance,
            "reason": reward.description
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"보상 지급 실패: {str(e)}")


# 6. 주식 매도 API (Sell)
@router.post("/sell")
async def sell_stock(trade: TradeRequest, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [매도 트랜잭션]
    1. 보유 주식 확인
    2. 주식 차감
    3. 잔액 증가
    4. 거래 장부 기록 (transactions 테이블)
    5. 경험치 및 퀘스트 보상 지급 (New!)
    """
    total_income = trade.price * trade.quantity
    
    try:
        await db.execute("BEGIN IMMEDIATE") # 트랜잭션 시작

        # 1. 내 주식고(Holdings) 확인
        cursor = await db.execute("""
            SELECT quantity, average_price 
            FROM holdings 
            WHERE user_id = ? AND company_name = ?
        """, (trade.user_id, trade.company_name))
        
        holding = await cursor.fetchone()
        
        # 주식이 아예 없거나, 팔려는 개수보다 적게 가지고 있다면?
        if not holding or holding[0] < trade.quantity:
            raise HTTPException(status_code=400, detail="매도할 주식이 부족합니다.")

        current_qty = holding[0]
        
        # 2. 주식 수량 차감
        new_qty = current_qty - trade.quantity
        
        # (사용자님의 좋은 습관: 수량이 0이 되어도 기록을 남김)
        await db.execute("""
            UPDATE holdings SET quantity = ? 
            WHERE user_id = ? AND company_name = ?
        """, (new_qty, trade.user_id, trade.company_name))

        # 3. 유저 잔액 증가 (돈 받기)
        cursor = await db.execute("SELECT balance FROM users WHERE id = ?", (trade.user_id,))
        row = await cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

        balance = row[0]
        new_balance = balance + total_income
        
        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, trade.user_id))

        # 4. 거래 원장(Ledger) 기록
        # (기존에 작성하신 꼼꼼한 기록 코드 유지)
        await db.execute("""
            INSERT INTO transactions (user_id, transaction_type, amount, balance_after, description)
            VALUES (?, 'SELL', ?, ?, ?)
        """, (trade.user_id, total_income, new_balance, f"{trade.company_name} {trade.quantity}주 매도"))

        await db.commit() # ✅ 여기서 DB 저장 완료!
        
        # 매도 보상 지급 (저장이 확실히 된 후 실행)
        try:
            # 1. 매도 경험치 20점 지급
            #await gain_exp(trade.user_id, 20)
            
            # 2. '첫 매도' 퀘스트 체크 (ID: trade_sell_first)
            await check_quest(trade.user_id, "trade_sell_first")
            
        except Exception as e:
            # 보상 지급 중 에러가 나도, 주식 판 건 취소되면 안 되니까 로그만 찍고 넘어감
            print(f"⚠️ 보상 지급 중 에러 발생: {e}")

        return {
            "status": "success",
            "message": f"{trade.company_name} {trade.quantity}주 매도 완료!",
            "balance": new_balance,
            "holdings": {"company": trade.company_name, "remaining_quantity": new_qty}
        }

    except HTTPException as he:
        await db.rollback()
        raise he
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"매도 실패: {str(e)}")


# 7. 지정가 주문 시스템 (Limit Order)

# 주문 요청 모델
class OrderRequest(BaseModel):
    user_id: int
    ticker: str = None          # 신규 방식
    company_name: str = None    # 기존 호환용
    order_type: str  
    price: int
    quantity: int

@router.post("/order")
async def place_order(req: OrderRequest):
    """
    사용자의 주문을 DB에 저장하고, 동시에 '진짜 엔진'으로 전송합니다.
    """
    # 호환성 처리: ticker가 없으면 company_name을 씁니다.
    target_ticker = req.ticker if req.ticker else req.company_name
    
    # 안전장치: 종목명이 아예 없으면 에러
    if not target_ticker:
        raise HTTPException(status_code=400, detail="종목명(ticker)이 필요합니다.")

    db = await get_db_connection()
    try:
        # 1. 유효성 및 자산 검증
        if req.price <= 0 or req.quantity <= 0:
            raise HTTPException(status_code=400, detail="가격과 수량은 양수여야 합니다.")

        if req.order_type == "BUY":
            total_cost = req.price * req.quantity
            cursor = await db.execute("SELECT balance FROM users WHERE id = ?", (req.user_id,))
            row = await cursor.fetchone()
            if not row or row['balance'] < total_cost:
                raise HTTPException(status_code=400, detail="현금이 부족합니다.")
            
            # 매수: 미리 돈 차감 (Locking)
            new_balance = row['balance'] - total_cost
            await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, req.user_id))
                
        elif req.order_type == "SELL":
            cursor = await db.execute("SELECT quantity FROM holdings WHERE user_id = ? AND company_name = ?", (req.user_id, target_ticker))
            row = await cursor.fetchone()
            if not row or row['quantity'] < req.quantity:
                raise HTTPException(status_code=400, detail="보유 주식이 부족합니다.")
            
            # 매도: 미리 주식 차감 (Locking)
            new_qty = row['quantity'] - req.quantity
            await db.execute("UPDATE holdings SET quantity = ? WHERE user_id = ? AND company_name = ?", (new_qty, req.user_id, target_ticker))

        # 2. DB에 'PENDING' 상태로 저장
        cursor = await db.execute("""
            INSERT INTO orders (user_id, company_name, order_type, price, quantity, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            RETURNING id
        """, (req.user_id, target_ticker, req.order_type, req.price, req.quantity))
        
        order_row = await cursor.fetchone()
        new_order_id = order_row[0]
        await db.commit()
        
        # 엔진으로 주문 전송!
        try:
            from main import engine
            
            side = OrderSide.BUY if req.order_type == "BUY" else OrderSide.SELL
            
            user_order = Order(
                agent_id=f"User_{req.user_id}",
                ticker=target_ticker,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=req.quantity,
                price=req.price
            )
            
            engine.place_order(user_order)
            print(f"🙋‍♂️ [사용자 주문] {target_ticker} {req.order_type} {req.quantity}주 @ {req.price}원 -> 엔진 전송 완료!")

        except Exception as e:
            print(f"⚠️ [전송 실패] 엔진 에러: {e}")

        return {"status": "success", "order_id": new_order_id, "msg": "주문이 정상 접수되었습니다."}

    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        print(f"❌ 주문 에러: {e}")
        raise HTTPException(status_code=500, detail="서버 에러")
    finally:
        await db.close()
@router.get("/orders/{user_id}")
async def get_my_orders(user_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [내 주문 내역 조회] 
    반드시 '아직 체결되지 않은(PENDING)' 주문만 가져와야 합니다.
    """
    cursor = await db.execute("""
        SELECT id, company_name, order_type, price, quantity, created_at, status
        FROM orders 
        WHERE user_id = ? AND status = 'PENDING' 
        ORDER BY created_at DESC
    """, (user_id,))
    
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]

@router.delete("/order/{order_id}")
async def cancel_order(order_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [주문 취소 - 디버깅 모드]
    서버가 보는 실제 데이터를 터미널에 출력합니다.
    """
    print(f"\n🔍 [주문 취소 시도] 요청된 주문 ID: {order_id}")
    
    try:
        await db.execute("BEGIN IMMEDIATE")
        
        # 1. 주문 조회
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        # dictionary 형태로 변환 (혹시 row_factory 설정 문제일 수 있으니 수동 변환)
        columns = [description[0] for description in cursor.description]
        row = await cursor.fetchone()
        
        if not row:
            print(f"❌ [오류] ID {order_id}번 주문이 DB에 아예 없습니다.")
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
            
        # 데이터를 딕셔너리로 만듦 (안전장치)
        order = dict(zip(columns, row))
        
        print(f"📄 [DB 데이터 확인] {order}")
        print(f"🧐 [상태 점검] DB에 저장된 상태: '{order['status']}'")

        # 2. 상태 확인 (공백 제거 후 비교)
        current_status = order['status'].strip()
        
        if current_status != 'PENDING':
            print(f"🚫 [거절] 상태가 PENDING이 아니라서 취소 불가. (현재: {current_status})")
            raise HTTPException(status_code=400, detail=f"취소 불가: 현재 상태가 '{current_status}' 입니다.")
            
        # 3. 환불 절차
        user_id = order['user_id']
        price = order['price']
        quantity = order['quantity']
        
        if order['order_type'] == 'BUY':
            refund = price * quantity
            await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (refund, user_id))
            print(f"💰 [환불] 유저 {user_id}에게 {refund}원 환불 완료")
            
        elif order['order_type'] == 'SELL':
            await db.execute("UPDATE holdings SET quantity = quantity + ? WHERE user_id = ? AND company_name = ?", (quantity, user_id, order['company_name']))
            print(f"📦 [반환] 유저 {user_id}에게 {order['company_name']} {quantity}주 반환 완료")
            
        # 4. 상태 변경
        await db.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
        await db.commit()
        
        print("✅ [성공] 주문 취소 및 환불 완료\n")
        return {"status": "success", "message": "주문이 취소되었습니다."}
        
    except HTTPException as he:
        await db.rollback()
        raise he
    except Exception as e:
        await db.rollback()
        print(f"🔥 [시스템 에러] {str(e)}")
        raise HTTPException(status_code=500, detail=f"서버 에러: {str(e)}")
    
# 테스트용 강제 체결 API (나중에 자동화될 예정)
@router.post("/process_orders")
async def process_market_price_change(company_name: str, current_price: float, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    [체결 엔진 시뮬레이션]
    특정 종목의 현재 가격이 변했다고 가정하고, 조건이 맞는 대기 주문을 체결시킵니다.
    - 매수 주문: 지정가 >= 현재가 (싸게 샀으니 이득, 체결)
    - 매도 주문: 지정가 <= 현재가 (비싸게 팔았으니 이득, 체결)
    """
    processed_count = 0
    
    try:
        await db.execute("BEGIN IMMEDIATE")
        
        # 1. 체결 가능한 매수 주문 찾기 (내가 건 가격보다 현재가가 싸거나 같으면 체결)
        cursor = await db.execute("""
            SELECT id, user_id, quantity, price FROM orders 
            WHERE company_name = ? AND order_type = 'BUY' AND status = 'PENDING' AND price >= ?
        """, (company_name, current_price))
        buy_orders = await cursor.fetchall()
        
        for order in buy_orders:
            # 주식 지급
            # (이미 holdings에 있는지 확인)
            h_cursor = await db.execute("SELECT quantity, average_price FROM holdings WHERE user_id = ? AND company_name = ?", (order['user_id'], company_name))
            holding = await h_cursor.fetchone()
            
            if holding:
                # 평단가 갱신 로직 (생략 가능하나 넣으면 좋음)
                new_qty = holding['quantity'] + order['quantity']
                # 평단가는 주문했던 가격(order['price'])으로 계산
                new_avg = ((holding['quantity'] * holding['average_price']) + (order['quantity'] * order['price'])) / new_qty
                await db.execute("UPDATE holdings SET quantity = ?, average_price = ? WHERE user_id = ? AND company_name = ?", (new_qty, new_avg, order['user_id'], company_name))
            else:
                await db.execute("INSERT INTO holdings (user_id, company_name, quantity, average_price) VALUES (?, ?, ?, ?)", (order['user_id'], company_name, order['quantity'], order['price']))
            
            # 주문 완료 처리
            await db.execute("UPDATE orders SET status = 'FILLED' WHERE id = ?", (order['id'],))
            
            # 거래 기록 남기기
            await db.execute("INSERT INTO transactions (user_id, transaction_type, amount, balance_after, description) VALUES (?, 'BUY', ?, 0, ?)", 
                             (order['user_id'], -(order['price'] * order['quantity']), f"{company_name} {order['quantity']}주 지정가 체결"))
            processed_count += 1

        # 2. 체결 가능한 매도 주문 찾기 (내가 건 가격보다 현재가가 비싸거나 같으면 체결)
        cursor = await db.execute("""
            SELECT id, user_id, quantity, price FROM orders 
            WHERE company_name = ? AND order_type = 'SELL' AND status = 'PENDING' AND price <= ?
        """, (company_name, current_price))
        sell_orders = await cursor.fetchall()
        
        for order in sell_orders:
            # 판매 대금 지급
            income = order['price'] * order['quantity']
            await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (income, order['user_id']))
            
            # 주문 완료 처리
            await db.execute("UPDATE orders SET status = 'FILLED' WHERE id = ?", (order['id'],))
            
            # 거래 기록
            await db.execute("INSERT INTO transactions (user_id, transaction_type, amount, balance_after, description) VALUES (?, 'SELL', ?, 0, ?)",
                             (order['user_id'], income, f"{company_name} {order['quantity']}주 지정가 체결"))
            processed_count += 1
            
        await db.commit()
        return {"status": "success", "message": f"{processed_count}건의 주문이 체결되었습니다."}
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, str(e))
    
# 🛑 [검문소 함수] 레벨 체크 디펜던시
async def verify_level_5(db: aiosqlite.Connection = Depends(get_db_connection)):
    user_id = 1  # (테스트용 고정 ID)
    cursor = await db.execute("SELECT level FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    
    current_level = row[0] if row else 1
    
    if current_level < 5:
        # 🚫 레벨 부족하면 403 에러 발생!
        raise HTTPException(
            status_code=403, 
            detail=f"🔒 호가창은 LV.5부터 이용 가능합니다. (현재: LV.{current_level})"
        )
    return True

# ✅ 호가창 API (검문소 통과해야 실행됨)
@router.get("/orderbook/{company_name}")
async def get_order_book(
    company_name: str, 
    is_authorized: bool = Depends(verify_level_5) # 👈 여기서 검사!
):
    """
    [호가창 조회]
    레벨 5 이상인 유저만 주식의 매수/매도 대기 물량을 볼 수 있습니다.
    """
    # (여기서는 실제 호가 데이터 대신 더미 데이터 반환)
    return {
        "company": company_name,
        "asks": [{"price": 81000, "qty": 10}, {"price": 82000, "qty": 50}], # 팔려는 사람
        "bids": [{"price": 79000, "qty": 20}, {"price": 78000, "qty": 100}] # 살려는 사람
    }