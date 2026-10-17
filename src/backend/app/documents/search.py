"""
[RAG 문서 검색 및 권한 필터링 엔진 - SearchRepository]
PostgreSQL의 pgvector와 지식 그래프(Graph RAG)를 결합하여,
사용자 권한(RLS) 범위 내에서 신뢰할 수 있는 팩트 패킷(FactPacket)을 추출하는 모듈입니다.
"""
import json, unicodedata
from uuid import UUID
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.policies.document_ingest import require_document_policy
from app.documents.policy import resolve_readable_version, DocumentUnavailable
from app.documents.storage import StoredSource
from app.documents.plan import build_document_plan
from app.documents.worker import local_id
from app.ai.token_limits import general_token_count, encoding
from common_core.ai_pipeline.document.schemas import DocumentMetadata
from common_core.ai_pipeline.graphrag.extractor import PROCESS_ALIASES
from common_core.ai_pipeline.graphrag.answer import FactPacket, select_relevant

# 문서 식별을 위한 4대 필수 키 (테넌트ID, 문서ID, 버전ID, 인덱스ID)
SOURCE_KEYS = ('source_tenant_id', 'document_id', 'version_id', 'index_id')

def source_binding(row):
    """DB 행 데이터를 문자열 딕셔너리로 안전하게 변환"""
    return {k: str(row[k]) for k in SOURCE_KEYS}

class SearchRepository:
    """
    RAG 검색 저장소:
    사용자의 권한 범위 내에서만 문서 청크와 지식 관계를 탐색하여 허위 인용을 원천 방지합니다.
    """
    def __init__(self, documents):
        self.documents = documents
        self.pool = documents.pool

    async def allowed(self, ctx, refs, mode, conn=None):
        """
        [1단계 권한 필터링]
        현재 세션 사용자가 읽기 권한(`security.document_can_read`)을 보유한 문서 목록만 선별합니다.
        - refs가 지정된 경우: 특정 선택 문서에 대한 권한 검증 (최대 5건)
        - refs가 없는 경우: 사용자가 접근 가능한 최신 공개 문서 목록 자동 조회 (최대 128건)
        """
        from contextlib import AsyncExitStack
        async with AsyncExitStack() as stack:
            if conn is None:
                conn = await stack.enter_async_context(tenant_transaction(self.pool, ctx))
            if refs:
                # 개별 문서 지정 모드: 중복 검사 및 최대 5개 제한
                if len(refs) > 5 or len({(str(x['document_id']), str(x['version_id'])) for x in refs}) != len(refs):
                    raise AppError('REQUEST_INVALID', 422)
                rows = []
                for ref in refs:
                    row = await (await conn.execute(
                        "SELECT v.tenant_id AS source_tenant_id, v.document_id, v.version_id, i.index_id "
                        "FROM rag.document_versions v "
                        "JOIN rag.index_builds i ON (i.tenant_id, i.document_id, i.version_id) = (v.tenant_id, v.document_id, v.version_id) "
                        "WHERE v.document_id = %s AND v.version_id = %s AND i.execution_mode = %s "
                        "AND security.document_can_read(v.tenant_id, v.document_id, v.version_id, i.index_id)",
                        (UUID(str(ref['document_id'])), UUID(str(ref['version_id'])), mode)
                    )).fetchone()
                    if row is None:
                        # 권한이 없거나 문서가 존재하지 않는 경우 404 차단
                        raise AppError('DOCUMENT_UNAVAILABLE', 404)
                    rows.append(row)
            else:
                # 전역 문서 모드: 사용자가 읽을 수 있는 최신 버전의 인덱스 검색
                rows = await (await conn.execute(
                    "SELECT DISTINCT ON(v.tenant_id, v.document_id) v.tenant_id AS source_tenant_id, v.document_id, v.version_id, i.index_id "
                    "FROM rag.document_versions v "
                    "JOIN rag.index_builds i ON (i.tenant_id, i.document_id, i.version_id) = (v.tenant_id, v.document_id, v.version_id) "
                    "WHERE security.document_can_read(v.tenant_id, v.document_id, v.version_id, i.index_id) "
                    "AND i.execution_mode = %s ORDER BY v.tenant_id, v.document_id, v.version_no DESC LIMIT 129",
                    (mode,)
                )).fetchall()
                if len(rows) > 128:
                    raise AppError('SEARCH_LIMIT_EXCEEDED', 409)
            return tuple(source_binding(x) for x in rows)

    async def guard(self, ctx, mode, sources):
        """검색 및 생성 직전 DB RPC를 통해 테넌트 격리와 권한 상태를 재확인"""
        return await self.documents.rpc(ctx, 'rag_sources_guard', (ctx.session_id, ctx.tenant_id, mode, Jsonb(list(sources))))

    async def packets(self, ctx, prompt, mode, sources, vector):
        """
        [2단계 벡터 및 지식 그래프 검색]
        질문 벡터와 문서 청크 간 코사인 유사도를 계산하고, 관련된 팩트 패킷(FactPacket)을 추출합니다.
        """
        # 질문 텍스트 정규화 및 업무 별칭(Alias) 치환
        question = unicodedata.normalize('NFC', prompt)
        for alias, value in sorted(PROCESS_ALIASES.items(), key=lambda x: -len(x[0])):
            question = question.replace(alias, value)

        indexes = [UUID(x['index_id']) for x in sources]
        scope = Jsonb(list(sources))

        # 권한이 확인된 문서 범위 내에서만 SQL 조회가 일어나도록 보장하는 조건절 매크로
        def allowed(alias):
            return (
                'EXISTS(SELECT 1 FROM jsonb_to_recordset(%s::jsonb) AS scope(source_tenant_id uuid,document_id uuid,version_id uuid,index_id uuid) '
                'WHERE (scope.source_tenant_id,scope.document_id,scope.version_id,scope.index_id)=('
                + alias + '.tenant_id,' + alias + '.document_id,' + alias + '.version_id,' + alias + '.index_id))'
            )

        async with tenant_transaction(self.pool, ctx) as conn:
            # 1. 보안 가드 실행
            await conn.execute('SELECT security.rag_sources_guard(%s,%s,%s,%s)', (ctx.session_id, ctx.tenant_id, mode, Jsonb(list(sources))))

            # 2. pgvector 코사인 거리(rag.<=>) 연산자로 질문 벡터와 가장 가까운 상위 6개 청크 검색
            chunks = await (await conn.execute(
                'SELECT tenant_id, index_id, chunk_id FROM rag.chunks c WHERE ' + allowed('c') +
                ' ORDER BY embedding OPERATOR(rag.<=>) %s::rag.vector, index_id, ordinal LIMIT 6',
                (scope, '[' + ','.join(str(x) for x in vector) + ']')
            )).fetchall()

            # 3. 질문과 연관된 엔티티(키워드/개념) 시드 추출
            personal_reference = len(sources) == 1 and '내' in question and '개인' in question and '리허설' in question
            seeds = await (await conn.execute(
                "SELECT tenant_id, index_id, entity_id, semantic_key FROM rag.entities e WHERE " + allowed('e') +
                " AND (strpos(%s, label) > 0 OR (%s AND entity_type = 'PERSON')) "
                "ORDER BY char_length(label) DESC, entity_id LIMIT 4",
                (scope, question, personal_reference)
            )).fetchall()

            # 4. 엔티티 간 관계(지식 그래프 Relation) 2-Hop 탐색
            keys = {x['semantic_key'] for x in seeds}
            relations = {}
            limited = False
            for hop in range(2):
                if not keys:
                    break
                rows = await (await conn.execute(
                    '''SELECT r.*, a.label AS subject, b.label AS value, a.semantic_key AS left_key, b.semantic_key AS right_key '''
                    '''FROM rag.relations r '''
                    '''JOIN rag.entities a ON (a.tenant_id, a.index_id, a.entity_id) = (r.tenant_id, r.index_id, r.from_entity_id) '''
                    '''JOIN rag.entities b ON (b.tenant_id, b.index_id, b.entity_id) = (r.tenant_id, r.index_id, r.to_entity_id) '''
                    '''WHERE ''' + allowed('r') + ''' AND (a.semantic_key = ANY(%s) OR b.semantic_key = ANY(%s)) '''
                    '''ORDER BY r.tenant_id, r.index_id, r.relation_id LIMIT 33''',
                    (scope, list(keys), list(keys))
                )).fetchall()
                for row in rows:
                    relations[(row['tenant_id'], row['index_id'], row['relation_id'])] = row
                if len(rows) > 32 or len(relations) > 32:
                    limited = True
                    break
                keys |= {x[k] for x in rows for k in ('left_key', 'right_key')}

            # 5. 검색된 관계 데이터를 실제 원본 문서의 원문 인용(Evidence)과 대조 및 패킷화
            packets = []
            plans = {}
            packet_ranks = {}
            chunk_ranks = {(x['tenant_id'], x['index_id'], x['chunk_id']): n for n, x in enumerate(chunks)}

            for row in list(relations.values())[:32]:
                rid = row['relation_id']
                idx = row['index_id']
                plan_key = (row['tenant_id'], idx)
                proofs = await (await conn.execute(
                    '''SELECT e.* FROM rag.relation_evidence re '''
                    '''JOIN rag.evidence e ON (e.tenant_id, e.index_id, e.evidence_id) = (re.tenant_id, re.index_id, re.evidence_id) '''
                    '''WHERE re.tenant_id = %s AND re.index_id = %s AND re.relation_id = %s ORDER BY e.evidence_id LIMIT 21''',
                    (row['tenant_id'], idx, rid)
                )).fetchall()
                if not proofs or len(proofs) > 20:
                    raise AppError('ANSWER_EVIDENCE_INVALID', 409)

                # 원본 문서 내용 로드 및 위변조 방지 SHA256 체크
                if plan_key not in plans:
                    v = await (await conn.execute(
                        'SELECT tenant_id, document_id, version_id, title, source_object_key, source_sha256, byte_length, character_length, media_type, source_mapping '
                        'FROM rag.document_versions WHERE tenant_id = %s AND version_id = %s',
                        (row['tenant_id'], row['version_id'])
                    )).fetchone()
                    if v is None:
                        raise AppError('DOCUMENT_UNAVAILABLE', 404)
                    raw = self.documents.storage.read(StoredSource(v['source_object_key'], bytes(v['source_sha256']), v['byte_length'], v['character_length'], v['title'], v['media_type'], v['source_mapping']))
                    require_document_policy(v["title"] + "\n" + raw.decode("utf-8"))
                    plan = build_document_plan(raw, v['title'], v['media_type'], DocumentMetadata(row['tenant_id'], row['document_id'], row['version_id'], idx, bytes(v['source_sha256']), mode))
                    i = await (await conn.execute('SELECT source_fingerprint, pipeline_revision FROM rag.index_builds WHERE tenant_id = %s AND index_id = %s', (row['tenant_id'], idx))).fetchone()
                    if i is None or bytes(i['source_fingerprint']).hex() != plan.source_fingerprint:
                        raise AppError('ANSWER_EVIDENCE_INVALID', 409)
                    plans[plan_key] = plan

                plan = plans[plan_key]
                expected = next((x for x in plan.graph.relations if local_id(idx, 'relation', x.ordinal) == rid), None)
                if expected is None or row['relation_type'] != expected.predicate or row['properties'] != dict(expected.properties) or row['from_entity_id'] != local_id(idx, 'entity', expected.from_ordinal) or row['to_entity_id'] != local_id(idx, 'entity', expected.to_ordinal) or {e['evidence_id'] for e in proofs} != {local_id(idx, 'evidence', x) for x in expected.evidence_ordinals}:
                    raise AppError('ANSWER_EVIDENCE_INVALID', 409)

                # 증거 단위(정확한 원문 인용구 및 시작/끝 줄번호 오프셋) 구성
                for proof in proofs:
                    original = next(x for x in plan.evidence if local_id(idx, 'evidence', x.ordinal) == proof['evidence_id'])
                    if proof['exact_quote'] != original.exact_quote or bytes(proof['source_sha256']) != plan.metadata.source_sha256 or any(proof[k] != getattr(original, k) for k in ('start_offset', 'end_offset', 'line_start', 'line_end')):
                        raise AppError('ANSWER_EVIDENCE_INVALID', 409)
                    evidence = {
                        **source_binding({**row, 'source_tenant_id': row['tenant_id']}),
                        'evidence_id': str(proof['evidence_id']),
                        'relation_id': str(rid),
                        'source_sha256': bytes(proof['source_sha256']).hex(),
                        'quote': proof['exact_quote'],
                        'location': {k: proof[k] for k in ('start_offset', 'end_offset', 'line_start', 'line_end')}
                    }
                    fact_key = 'F' + str(len(packets))
                    packet_ranks[fact_key] = chunk_ranks.get((row['tenant_id'], idx, proof['chunk_id']), len(chunks))
                    # AI가 참조할 단일 팩트 단위(FactPacket) 생성 (예: F0, F1...)
                    packets.append(FactPacket(fact_key, expected.predicate, plan.graph.entities[expected.from_ordinal].canonical_label, plan.graph.entities[expected.to_ordinal].canonical_label, expected.properties, evidence, str(row['tenant_id'])))

        # 6. 질문과의 관련도 순으로 팩트 정렬 및 선별
        packets.sort(key=lambda packet: packet_ranks[packet.fact_id])
        relevant, required = select_relevant(question, packets, limited)

        # 7. 토큰 한도(2,000 토큰) 초과 방지 가드
        context = json.dumps([p.public() for p in relevant], ensure_ascii=False, separators=(',', ':'))
        if len(encoding('o200k_base').encode(context, disallowed_special=())) > 2000:
            return (), required
        return relevant, required
