"""Pure fact selection and rendering. Provider cannot invent text or citations."""
import json
from dataclasses import dataclass,field

class AnswerInvalid(ValueError):pass
@dataclass(frozen=True)
class FactPacket:
    fact_id:str
    predicate:str
    subject:str
    value:str
    properties:tuple
    evidence:dict=field(repr=False)
    namespace:str
    def public(self):return {'fact_id':self.fact_id,'predicate':self.predicate,'subject':self.subject,'value':self.value,'conditions':dict(self.properties),'quote':self.evidence['quote']}

PREDICATES=(('위험 검토 승인','위험검토승인부서'),('기록 보관 담당','기록보관담당부서'),('기록 보관 기간','기록보관기간'),('점검표','필수점검표'),('누락','누락점검일'),('리허설','개인리허설일정'),('접수 확인','접수확인기한'),('접수 담당','접수담당'),('복구 목표','복구목표'))
def required_predicates(prompt):
    text=''.join(prompt.split());needed=[p for phrase,p in PREDICATES if ''.join(phrase.split()) in text]
    if '누락점검일' in needed:needed.append('기록보관담당부서')
    if '접수확인기한' in needed:needed.append('접수담당')
    if not needed and '담당' in text:needed=['담당부서']
    return tuple(dict.fromkeys(needed))

def select_relevant(prompt,packets,limited=False):
    required=required_predicates(prompt)
    if not required or limited:return (),required
    root=tuple(p for p in packets if p.predicate in required and p.predicate not in ('누락점검일','접수확인기한') and p.subject in prompt)
    selected=root+tuple(p for p in packets if p.predicate in required and p.predicate in ('누락점검일','접수확인기한') and (p.subject in prompt or any(a.namespace==p.namespace and a.value==p.subject for a in root)))
    if set(required)-{p.predicate for p in selected}:return (),required
    groups={}
    for p in selected:
        key=(p.subject,p.predicate);groups.setdefault(key,set()).add((p.value,p.properties))
    if any(len(v)>1 for v in groups.values()):return (),required
    # Multi-hop responsibility must belong to one owner namespace and explicit team link.
    for first,second in [('기록보관담당부서','누락점검일'),('접수담당','접수확인기한')]:
        if second in required and not any(a.namespace==b.namespace and a.value==b.subject and (second!='누락점검일' or dict(b.properties).get('process')==a.subject) for a in selected if a.predicate==first for b in selected if b.predicate==second):return (),required
    if len(selected)>20:return (),required
    return selected,required

def _unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise AnswerInvalid('ANSWER_EVIDENCE_INVALID')
        d[k]=v
    return d

def render_answer(raw,packets,required):
    try:
        d=json.loads(raw,object_pairs_hook=_unique)
        if type(d)!=dict or set(d)!={'answer_kind','selected_fact_ids'} or d['answer_kind'] not in ('answer','insufficient_evidence') or type(d['selected_fact_ids'])!=list or len(d['selected_fact_ids'])>20 or any(type(x)!=str for x in d['selected_fact_ids']) or len(set(d['selected_fact_ids']))!=len(d['selected_fact_ids']):raise AnswerInvalid()
        if d['answer_kind']=='insufficient_evidence':
            if d['selected_fact_ids']:raise AnswerInvalid()
            return '허용된 자료에서 답을 확인할 충분한 근거가 없습니다.',(),d['answer_kind']
        by_id={p.fact_id:p for p in packets};chosen=tuple(by_id[x] for x in d['selected_fact_ids'])
        if not chosen or set(required)-{p.predicate for p in chosen}:raise AnswerInvalid()
        # Model cannot select only an unrelated team for a required linked path.
        for first,second in [('기록보관담당부서','누락점검일'),('접수담당','접수확인기한')]:
            if second in required and not any(a.namespace==b.namespace and a.value==b.subject and (second!='누락점검일' or dict(b.properties).get('process')==a.subject) for a in chosen if a.predicate==first for b in chosen if b.predicate==second):raise AnswerInvalid()
        rows=[];proofs=[]
        for p in chosen:
            if p.evidence not in proofs:proofs.append(p.evidence)
            citation=proofs.index(p.evidence)+1
            condition=' ('+'; '.join(k+': '+v for k,v in p.properties)+')' if p.properties else ''
            rows.append(f'{p.subject}의 {p.predicate}: {p.value}{condition} [{citation}]')
        return '\n'.join(rows),tuple(proofs),'answer'
    except (ValueError,TypeError,KeyError,UnicodeError):raise AnswerInvalid('ANSWER_EVIDENCE_INVALID') from None
