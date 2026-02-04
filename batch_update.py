import time
from database import init_db
from news_manager import save_news_to_db
from agent_service import StockAgentService

# 섹터별 기업 리스트
SECTOR_COMPANIES = {
    "IT": ["삼성전자", "마이크로소프트 (Microsoft)"]
}

def run_full_update():
    init_db() # DB 초기화
    agent = StockAgentService(mode="real")
    
    print("🚀 [Money Quest] 테스트용 뉴스 수집을 시작합니다...")

    for sector, companies in SECTOR_COMPANIES.items():
        print(f"\n📂 {sector} 섹터 분석 중...")
        for company in companies:
            try:
                print(f"🔍 {company} 뉴스 분석 중...", end="", flush=True)
                
                # AI 에이전트 호출
                news_data = agent.analyze_stock_news(company, count=2)
                
                if isinstance(news_data, list):
                    save_news_to_db(company, news_data) # DB 저장
                    print(f" -> ✅ {len(news_data)}개 저장 완료")
                else:
                    print(f" -> ⚠️ 리스트 형식이 아닙니다: {news_data}")

                # API 호출 간격 유지
                time.sleep(2)
                
            except Exception as e:
                print(f" -> ❌ 에러 발생: {e}")

    print("\n✨ 테스트 데이터 수집이 완료되었습니다!")

if __name__ == "__main__":
    run_full_update()