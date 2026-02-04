import time
from agent_service import StockAgentService
from database import init_db
from news_manager import save_news_to_db

# 가상 기업 리스트
VIRTUAL_COMPANIES = [
    {"name": "상은테크놀로지", "sector": "IT"},
    {"name": "약방임돠", "sector": "제약"},
    {"name": "JPY", "sector": "엔터"}
]

def run_bulk_generation():
    init_db()
    # 가상 모드로 에이전트 시작
    agent = StockAgentService(mode="virtual")
    
    print("🎨 [Money Quest] 가상 뉴스 세계관 생성을 시작합니다...")

    for comp in VIRTUAL_COMPANIES:
        print(f"✍️ {comp['name']} 기사 작성 요청 중...", end="", flush=True)
        
        
        result = agent.analyze_stock_news(comp['name'], mode="virtual", count=2) 
        
        if isinstance(result, list):
            save_news_to_db(comp['name'], result)
        else:
            print(f" -> ❌ 생성 실패: {result.get('error')}")
            
        time.sleep(1)

    print("\n✨ 모든 가상 기업의 뉴스가 DB에 통합 저장되었습니다!")

if __name__ == "__main__":
    run_bulk_generation()