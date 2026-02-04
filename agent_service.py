import os
import json
import time
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

load_dotenv()

class StockAgentService:
    def __init__(self, mode="real"):
        # 1. 공통 설정 로드
        self.conn_str = os.getenv("PROJECT_CONNECTION_STRING")
        
        # 2. 모드에 따른 에이전트 ID 설정
        if mode == "virtual":
            self.agent_id = os.getenv("VIRTUAL_AGENT_ID")
            print(f"🤖 가상 뉴스 생성 모드 (4o-mini) 활성화")
        else:
            self.agent_id = os.getenv("REAL_AGENT_ID")
            print(f"📡 실제 뉴스 분석 모드 (4o) 활성화")

        # 3. 클라이언트 초기화 (한 번만 수행하여 효율성 높임)
        self.project_client = AIProjectClient.from_connection_string(
            conn_str=self.conn_str,
            credential=DefaultAzureCredential()
        )

    def analyze_stock_news(self, company_name: str, mode="real", count=20):
        # 1. 모드에 따른 프롬프트 생성 (동일)
        if mode == "virtual":
            prompt = (
                f"너는 주식 게임 작가야. 가상 기업 '{company_name}'에 대한 "
                f"주가 영향 뉴스 {count}개를 지어내줘. 호재와 악재를 정확히 반반씩 섞어줘. "
                f"형식은 반드시 [{{'title': '..', 'summary': '..', 'impact_score': 숫자, 'reason': '..'}}] 이여야 해."
            )
        else:
            prompt = f"'{company_name}'의 최신 뉴스 {count}개를 분석해서 JSON 리스트로 출력해줘."
        
        # 2. 분석 수행
        # 이제 self.project_client를 직접 사용합니다.
        thread = self.project_client.agents.create_thread()
        
        self.project_client.agents.create_message(
            thread_id=thread.id,
            role="user",
            content=prompt
        )

        run = self.project_client.agents.create_run(thread_id=thread.id, assistant_id=self.agent_id)
        
        while run.status in ["queued", "in_progress"]:
            time.sleep(1)
            run = self.project_client.agents.get_run(thread_id=thread.id, run_id=run.id)

        if run.status == "completed":
            messages = self.project_client.agents.list_messages(thread_id=thread.id)
            last_msg = messages.data[0].content[0].text.value
            
            try:
                clean_json = last_msg.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_json)
            except:
                return {"error": "JSON 파싱 실패", "raw": last_msg}
        else:
            return {"error": f"분석 실패: {run.status}"}