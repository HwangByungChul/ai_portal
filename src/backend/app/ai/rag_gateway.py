"""
[AI 호출 및 원장 계측 게이트웨이 - QueryGateway & generation]
사용자 질문 임베딩 생성 및 LLM 답변 호출 시, 사내 토큰 한도를 체크하고
실시간 사용 비용/호출 이력을 중앙 원장(Ledger)에 투명하게 계측·기록하는 안전 관문입니다.
"""
import asyncio, hashlib, json, secrets
from dataclasses import asdict
from uuid import UUID
from psycopg.types.json import Jsonb
from app.ai.repository import CallRepository, ExecutionError, DispatchUncertain, digest
from app.ai.gateway import AiGateway
from app.ai.types import DispatchClaim, ProviderOutcome
from app.ai.pricing import cost_krw
from app.ai.token_limits import count_embedding_tokens, general_token_count
from app.documents.embedding import vector_values

class RagCallRepository(CallRepository):
    """RAG 호출 예약 및 상태 변경을 DB에 기록하는 전용 리포지토리"""
    def __init__(self, repository, operation, sources):
        super().__init__(repository.web_pool, repository.meter_pool, repository.period)
        self.operation = operation
        self.sources = sources

    async def reserve(self, ticket, fingerprint):
        """API 호출 전, 예산 및 테넌트 한도를 체크하여 호출 슬롯을 사전 예약"""
        return await self._rpc(
            self.web_pool,
            'summary_call_reserve' if ticket.task_kind == 'document_summary' else 'rag_call_reserve',
            (*self.worker_args(ticket), self.period, fingerprint, self.operation, Jsonb(list(self.sources))),
            ticket.ctx
        )

class QueryGateway:
    """
    [질문 임베딩 변환기]
    사용자 질문 텍스트를 AI 모델에 전달하여 검색용 수치 벡터(Embedding Vector)로 안전하게 변환합니다.
    """
    def __init__(self, repository, provider):
        self.repository = repository
        self.provider = provider
        self.stop_latch = False  # 과금 시스템 장애 등 비상 상황 시 호출을 긴급 차단하는 래치

    async def execute(self, ticket, prompt, sources):
        """
        질문 텍스트를 임베딩 벡터로 변환하는 메인 함수
        - 토큰 한도(최대 4,000자/토큰) 검사
        - 호출 사전 예약 및 원장(Ledger) 승인
        - 외부 AI API 호출 (최대 60초 타임아웃)
        - 사용량 및 원화 비용(KRW) 정산
        """
        if self.stop_latch:
            raise ExecutionError('PROJECT_STOPPED')

        # 1. 질문 토큰 수 계산 및 과다 입력 방지
        tokens = count_embedding_tokens(prompt)
        if tokens > 4000:
            raise ExecutionError('TOKEN_LIMIT_EXCEEDED')

        repo = RagCallRepository(self.repository, 'embed_query', sources)
        fingerprint = hashlib.sha256(prompt.encode()).digest()
        call = None
        claim = None

        try:
            # 2. 호출 예약 (DB에 호출 준비 상태 등록)
            data = await repo.reserve(ticket, fingerprint)
            call = UUID(data['call_id'])
            if not data['created']:
                raise ExecutionError('EXECUTION_BLOCKED')

            # 3. 호출 권한 디스패치 확인
            claim = await repo.dispatch(ticket, call)
            if claim is None:
                raise ExecutionError('EXECUTION_BLOCKED')

            try:
                # 4. 외부 AI 임베딩 API 호출 (60초 타임아웃)
                async with asyncio.timeout(60):
                    values, receipt = await self.provider.embed(claim.call_id, [prompt], tokens)

                # 5. 수치 벡터 추출 및 원화 비용 계산
                vector = vector_values(values, 1)[0]
                cost_krw(receipt)

                # 6. 원장 정산 (사용된 토큰 및 비용 최종 확정)
                status = await repo.settle(ticket, claim, receipt, 'observed')
                if status['state'] != 'settled' or status['invalid'] or status['conflict'] or status['overrun']:
                    raise ExecutionError('LEDGER_UNAVAILABLE')
                return vector

            except BaseException:
                # 네트워크 장애 등으로 실패 시 미정 상태로 마킹
                try:
                    await repo.mark_unknown(ticket, claim)
                except BaseException:
                    self.stop_latch = True
                raise

        except DispatchUncertain as error:
            self.stop_latch = True
            try:
                await repo.mark_unknown(ticket, error.claim)
            except BaseException:
                pass
            raise ExecutionError('LEDGER_UNAVAILABLE') from None

        finally:
            # 호출이 시작되지 않고 취소된 경우 예약 슬롯 해제
            if call is not None and claim is None:
                try:
                    await repo.release_unfired(ticket, call)
                except ExecutionError:
                    self.stop_latch = True

async def generation(repository, provider, ticket, sources, messages):
    """
    [LLM 최종 답변 생성 호출]
    검색된 팩트가 포함된 최종 프롬프트를 LLM(GPT 등)에 전달하여 답변을 수신합니다.
    - 비용 원장과 실시간 연동되어 모든 생성이 안전하게 계측됩니다.
    """
    repo = RagCallRepository(repository, 'generate_rag', sources)
    gateway = AiGateway(repo, provider)

    from dataclasses import replace
    async def buffer_only(text):
        pass  # 단일 완료형 응답 버퍼 처리

    # AI 게이트웨이를 통해 정식 생성 실행
    outcome = await gateway.execute(replace(ticket, messages=messages), buffer_only)

    # 과금 원장 시스템 장애 발생 시 비상 안전 코드 반환
    if gateway.stop_latch:
        code = outcome.safe_error_code if outcome.safe_error_code in ('LEDGER_UNAVAILABLE', 'LEDGER_CONFLICT', 'USAGE_INVALID', 'PROJECT_STOPPED') else 'LEDGER_UNAVAILABLE'
        return ProviderOutcome(None, outcome.receipt, outcome.end_status, code)

    return outcome
