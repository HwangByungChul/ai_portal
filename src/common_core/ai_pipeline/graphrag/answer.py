"""
[RAG 출처 검증 및 환각(거짓말) 차단 엔진 - render_answer]
AI 모델(LLM)이 생성한 답변이 실제 검색된 문서 팩트(Fact)에 기반한 것인지 엄격히 검증하고,
검증된 팩트 번호에 맞춰 정확한 출처(인용구, 페이지, 문서)를 확정하는 환각 방지 모듈입니다.
"""
import json
from dataclasses import dataclass, field

class AnswerInvalid(ValueError):
    """AI 모델이 가짜 인용을 하거나 근거 없는 내용을 응답했을 때 발생하는 예외"""
    pass

@dataclass(frozen=True)
class FactPacket:
    """
    [단일 팩트 패킷]
    문서에서 추출된 하나의 사실 조각을 나타냅니다.
    예: (주어: '여비 규정', 서술어: '출장일비', 값: '일 30,000원', 출처: '사규 15페이지 3행')
    """
    fact_id: str                      # 고유 팩트 식별자 (F0, F1, F2...)
    predicate: str                    # 관계 서술어 (예: '기록보관기간', '담당부서')
    subject: str                      # 주어 대상 (예: '보안점검표', '프로젝트')
    value: str                        # 사실 값 (예: '5년', '정보보호팀')
    properties: tuple                 # 추가 세부 속성/조건
    evidence: dict = field(repr=False)# 실제 원본 문서 증거 (문서ID, 원문 인용문, 페이지/줄 오프셋)
    namespace: str                    # 테넌트/소속 식별자

    def public(self):
        """AI 모델에게 프롬프트로 전달하기 위한 공개용 요약 사전"""
        return {
            'fact_id': self.fact_id,
            'predicate': self.predicate,
            'subject': self.subject,
            'value': self.value,
            'conditions': dict(self.properties),
            'quote': self.evidence['quote']
        }

# 업무 온톨로지 관계 키워드 매핑 테이블
PREDICATES = (
    ('위험 검토 승인', '위험검토승인부서'),
    ('기록 보관 담당', '기록보관담당부서'),
    ('기록 보관 기간', '기록보관기간'),
    ('점검표', '필수점검표'),
    ('누락', '누락점검일'),
    ('리허설', '개인리허설일정'),
    ('접수 확인', '접수확인기한'),
    ('접수 담당', '접수담당'),
    ('복구 목표', '복구목표')
)

def required_predicates(prompt):
    """
    사용자의 질문 텍스트를 분석하여, 답변을 구성하는 데 반드시 포함되어야 할 핵심 관계(Predicate)들을 도출합니다.
    """
    text = ''.join(prompt.split())
    # 업무 정의 범위를 벗어나는 질문은 엉뚱한 연관 답변 방지를 위해 차단
    if any(word in text for word in ('금리', '금액상한', '파기승인', '파기승인자')):
        return ()
    needed = [p for phrase, p in PREDICATES if ''.join(phrase.split()) in text]
    if '보관' in text and any(word in text for word in ('며칠', '기간')):
        needed.append('기록보관기간')
    if '기록보관' in text and ('부서' in text or '맡' in text) and '기간' not in text:
        needed.append('기록보관담당부서')
    if '담당부서' in text:
        without_roles = text.replace('기록보관담당부서', '').replace('위험검토승인부서', '')
        if '담당부서' in without_roles:
            needed.append('담당부서')
    if '누락점검일' in needed:
        needed.append('기록보관담당부서')
    if '접수확인기한' in needed:
        needed.append('접수담당')
    if not needed and '담당' in text:
        needed = ['담당부서']
    return tuple(dict.fromkeys(needed))

def select_relevant(prompt, packets, limited=False):
    """
    검색된 수많은 팩트 조각 중에서 질문 요구 조건(`required_predicates`)에 정확히 부합하는 유효 팩트만 선별합니다.
    """
    required = required_predicates(prompt)
    if not required or limited:
        return (), required
    personal = tuple(p for p in packets if p.predicate == '개인리허설일정')
    personal_reference = '내' in prompt and '개인' in prompt and '리허설' in prompt and len(personal) == 1
    root = tuple(p for p in packets if p.predicate in required and p.predicate not in ('누락점검일', '접수확인기한') and (p.subject in prompt or (personal_reference and p.predicate == '개인리허설일정')))
    selected = root + tuple(p for p in packets if p.predicate in required and p.predicate in ('누락점검일', '접수확인기한') and (p.subject in prompt or any(a.namespace == p.namespace and a.value == p.subject for a in root)))
    if set(required) - {p.predicate for p in selected}:
        return (), required
    groups = {}
    for p in selected:
        key = (p.subject, p.predicate)
        groups.setdefault(key, set()).add((p.value, p.properties))
    if any(len(v) > 1 for v in groups.values()):
        return (), required
    for first, second in [('기록보관담당부서', '누락점검일'), ('접수담당', '접수확인기한')]:
        if second in required and not any(a.namespace == b.namespace and a.value == b.subject and (second != '누락점검일' or dict(b.properties).get('process') == a.subject) for a in selected if a.predicate == first for b in selected if b.predicate == second):
            return (), required
    if len(selected) > 20:
        return (), required
    return selected, required

def _unique(pairs):
    """JSON 파싱 시 키 중복이 발생하면 즉시 예외를 발생시키는 엄격 파서"""
    d = {}
    for k, v in pairs:
        if k in d:
            raise AnswerInvalid('ANSWER_EVIDENCE_INVALID')
        d[k] = v
    return d

def render_answer(raw, packets, required):
    """
    [핵심 검증 함수: AI 답변 렌더링 및 출처 바인딩]
    1. AI가 반환한 JSON 구조(답변 유형, 선택한 팩트ID 목록) 검사
    2. AI가 인용한 fact_id(예: F0, F1)가 실제 제공된 팩트 목록에 존재하는지 전수 검증
    3. AI가 지어낸 번호나 누락이 발견되면 'AnswerInvalid' 에러 발생
    4. 검증 통과 시 문장에 번호 각주([1], [2]...)를 달고 실제 문서 출처 목록을 결합하여 반환
    """
    try:
        d = json.loads(raw, object_pairs_hook=_unique)
        # 응답 규격이 올바른지 엄격히 확인
        if type(d) != dict or set(d) != {'answer_kind', 'selected_fact_ids'} or d['answer_kind'] not in ('answer', 'insufficient_evidence') or type(d['selected_fact_ids']) != list or len(d['selected_fact_ids']) > 20 or any(type(x) != str for x in d['selected_fact_ids']) or len(set(d['selected_fact_ids'])) != len(d['selected_fact_ids']):
            raise AnswerInvalid()

        # AI가 근거 부족이라고 판단한 경우
        if d['answer_kind'] == 'insufficient_evidence':
            if d['selected_fact_ids']:
                raise AnswerInvalid()
            return '허용된 자료에서 답을 확인할 충분한 근거가 없습니다.', (), d['answer_kind']

        # AI가 인용한 팩트 ID 대조
        by_id = {p.fact_id: p for p in packets}
        chosen = tuple(by_id[x] for x in d['selected_fact_ids'])
        if not chosen or set(required) - {p.predicate for p in chosen}:
            raise AnswerInvalid()

        # 연계 관계 유효성 검사
        for first, second in [('기록보관담당부서', '누락점검일'), ('접수담당', '접수확인기한')]:
            if second in required and not any(a.namespace == b.namespace and a.value == b.subject and (second != '누락점검일' or dict(b.properties).get('process') == a.subject) for a in chosen if a.predicate == first for b in chosen if b.predicate == second):
                raise AnswerInvalid()

        # 각주 번호([1], [2])와 출처 문서 정보(proofs) 연결
        rows = []
        proofs = []
        for p in chosen:
            if p.evidence not in proofs:
                proofs.append(p.evidence)
            citation = proofs.index(p.evidence) + 1
            condition = ' (' + '; '.join(k + ': ' + v for k, v in p.properties) + ')' if p.properties else ''
            rows.append(f'{p.subject}의 {p.predicate}: {p.value}{condition} [{citation}]')

        # 검증 완료된 답변 본문, 실제 문서 출처 목록, 성공 상태 반환
        return '\n'.join(rows), tuple(proofs), 'answer'

    except (ValueError, TypeError, KeyError, UnicodeError):
        # AI 응답 형식이 깨졌거나 검증 실패 시 환각 에러 발생
        raise AnswerInvalid('ANSWER_EVIDENCE_INVALID') from None
