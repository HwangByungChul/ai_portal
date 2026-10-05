"""GR01-10 whole-sentence positive declarations. No LLM or inferred facts."""
from dataclasses import replace
import hashlib
import re
import unicodedata
from .schemas import Entity,Relation,GraphPlan
from ..document.schemas import PlanError

PROCESS_ALIASES={'가상 여신심사':'여신심사','여신심사':'여신심사',
    '가상 AI 지원 요청':'AI 지원 요청','AI 지원 요청':'AI 지원 요청','지원 절차':'AI 지원 요청',
    '가상 AI 서비스':'AI 지원 요청'}
RULES=(
 ('GR03','PROCESS','TEAM','기록보관담당부서',r'(?P<s>.+?)의 기록 보관 담당 부서는 (?P<t>.+?)이다\.'),
 ('GR02','PROCESS','TEAM','위험검토승인부서',r'(?P<s>.+?)의 위험 검토 승인 부서는 (?P<t>.+?)이다\.'),
 ('GR01','PROCESS','TEAM','담당부서',r'(?P<s>.+?)의 담당 부서는 (?P<t>.+?)이다\.'),
 ('GR04','PROCESS','DURATION','기록보관기간',r'(?P<s>.+?)의 기록 보관 기간은 (?P<t>\d+(?:영업일|일|시간|분|개월|년))이다\.'),
 ('GR05','PROCESS','ARTIFACT','필수점검표',r'(?P<s>.+?)(?:은|는) (?:(?P<condition>.+? 전에) )?(?P<t>.*?점검표)를 작성한다\.'),
 ('GR06','TEAM','SCHEDULE','누락점검일',r'(?P<s>.+?)(?:은|는) (?P<process>.+?) 기록의 누락 여부를 (?P<t>.+?)에 점검한다\.'),
 ('GR07','PERSON','SCHEDULE','개인리허설일정',r'(?P<s>.+?)의 개인 시연 리허설은 (?P<t>.+?)에 진행한다\.'),
 ('GR08','PROCESS','TEAM','접수담당',r'(?P<s>.+?)의 접수 담당은 (?P<t>.+?)이다\.'),
 ('GR09','TEAM','DURATION','접수확인기한',r'(?P<s>.+?)(?:은|는) 요청 접수 후 (?P<t>\d+(?:영업일|일|시간|분)) 이내에 접수 확인을 통보한다\.'),
 ('GR10','PROCESS','DURATION','복구목표',r'(?P<s>.+?)의 복구 목표는 (?P<t>\d+(?:영업일|일|시간|분))이다\.'),
)
DIRECTIONS={p:(left,right) for _,left,right,p,_ in RULES}


def canonical(kind,label):
    value=' '.join(unicodedata.normalize('NFC',label).split())
    return PROCESS_ALIASES.get(value,value) if kind=='PROCESS' else value


def semantic_key(metadata,kind,label):
    value=str(metadata.tenant_id)+'\0'+kind+'\0'+canonical(kind,label)
    return hashlib.sha256(value.encode()).hexdigest()


def extract_graph(source,chunks,evidence,metadata) -> GraphPlan:
    entities=[];entity_map={};relations=[];relation_map={};reasons=[]
    units={u.ordinal:u for c in chunks for u in c.units}
    def entity(kind,label):
        label=' '.join(label.split());key=(kind,canonical(kind,label))
        if key not in entity_map:
            entity_map[key]=len(entities)
            entities.append(Entity(len(entities),kind,label,key[1],semantic_key(metadata,kind,label),metadata))
            if len(entities)>512:raise PlanError('INDEX_LIMIT_EXCEEDED')
        return entity_map[key]
    candidates=[]
    for ev in evidence:
        unit=units[ev.unit_ordinal]
        if unit.kind!='body':reasons.append((ev.ordinal,'NON_BODY'));continue
        if not ev.complete:reasons.append((ev.ordinal,'INCOMPLETE_SPAN'));continue
        text=' '.join(ev.exact_quote.split())
        if re.search(r'아니|않|없|예외|경우|제외|만약|또는|할 수|권고|예정|하면|라면|따라|조건|일 때',text) or re.match(r'^(?:그|그녀|해당 부서|담당자)(?:은|는|의|가|이)',text):
            reasons.append((ev.ordinal,'UNSUPPORTED_QUALIFIER'));continue
        matched=False
        for rule,left,right,predicate,pattern in RULES:
            match=re.fullmatch(pattern,text)
            if not match:continue
            fields=match.groupdict()
            if (any(not 1<=len(fields[k])<=200 for k in ['s','t'])
                    or any(re.search(r'[,;/]| 및 | 그리고 |의 담당|의 위험|의 기록',fields[k]) for k in ['s','t'])):
                reasons.append((ev.ordinal,'AMBIGUOUS_LABEL'));matched=True;break
            candidates.append((rule,left,right,predicate,fields,ev));matched=True;break
        if not matched:reasons.append((ev.ordinal,'UNSUPPORTED_SENTENCE'))
    if any(re.search(r'예외|경우|제외|만약|하면|라면',e.exact_quote) for e in evidence if e.complete):
        reasons.extend((ev.ordinal,'UNSCOPED_EXCEPTION') for *_,ev in candidates)
        candidates=[]
    # GR06 links a process only when same-document explicit record responsibility supports it.
    responsibilities={(canonical('PROCESS',f['s']),canonical('TEAM',f['t'])) for rule,_,_,_,f,_ in candidates if rule=='GR03'}
    for rule,left,right,predicate,fields,ev in candidates:
        props=[]
        if rule=='GR06':
            if (canonical('PROCESS',fields['process']),canonical('TEAM',fields['s'])) not in responsibilities:
                reasons.append((ev.ordinal,'MISSING_RESPONSIBILITY'));continue
            props.append(('process',canonical('PROCESS',fields['process'])))
        if fields.get('condition'):props.append(('condition',fields['condition']))
        if rule=='GR09':props.extend([('relative_trigger','요청 접수 후'),('qualifier','이내')])
        start,end=entity(left,fields['s']),entity(right,fields['t']);props=tuple(sorted(props))
        key=(start,predicate,end,props)
        if key in relation_map:
            pos=relation_map[key];old=relations[pos]
            relations[pos]=replace(old,evidence_ordinals=old.evidence_ordinals+(ev.ordinal,))
        else:
            relation_map[key]=len(relations)
            relations.append(Relation(len(relations),rule,start,end,predicate,props,(ev.ordinal,),metadata))
        if len(relations)>1024 or sum(len(r.evidence_ordinals) for r in relations)>2048:raise PlanError('INDEX_LIMIT_EXCEEDED')
    groups={}
    for rel in relations:groups.setdefault((rel.from_ordinal,rel.predicate,rel.properties),set()).add(rel.to_ordinal)
    valid=[]
    for rel in relations:
        if len(groups[(rel.from_ordinal,rel.predicate,rel.properties)])>1:
            reasons.extend((e,'CONFLICTING_VALUES') for e in rel.evidence_ordinals)
        else:valid.append(rel)
    # Do not retain schedules based on a responsibility rejected as conflicting.
    valid_responsibilities={(entities[r.from_ordinal].canonical_label,entities[r.to_ordinal].canonical_label) for r in valid if r.rule_id=='GR03'}
    retained=[]
    for rel in valid:
        if rel.rule_id=='GR06' and (dict(rel.properties)['process'],entities[rel.from_ordinal].canonical_label) not in valid_responsibilities:
            reasons.extend((e,'MISSING_RESPONSIBILITY') for e in rel.evidence_ordinals)
        else:retained.append(replace(rel,ordinal=len(retained)))
    return GraphPlan(metadata,tuple(entities),tuple(retained),'partial' if reasons or source.warnings else 'complete',tuple(sorted(set(reasons))))
