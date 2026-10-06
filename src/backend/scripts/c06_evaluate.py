"""Evaluator-only Q20 runner. Never passes gold facts/IDs to runtime requests.

CLI owns a newly marked disposable database and source directory, uses Mock only,
and reports failures without changing the authored corpus or primary environment.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'src/backend'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def normalized(text):return ''.join(unicodedata.normalize('NFC',text).split())

def runtime_payload(question,mapping):
    body={'agent_key':'rules_rag','prompt':question['prompt'],'client_send_id':str(uuid4())}
    ref=question['request_fixture']['target_reference']
    if ref:
        actual=mapping[(ref['document_id'],ref['version'])]
        body['document_refs']=[{k:actual[k] for k in ('document_id','version_id')}]
    return body

def map_evidence(items,manifest,mapping):
    found=[];invalid=[]
    for item in items:
        if item.get('content_status')!='available':invalid.append('unavailable_evidence');continue
        candidates=[]
        for gold in manifest['evidence']:
            actual=mapping[(gold['document_id'],gold['version'])]
            if (item.get('document_id'),item.get('version_id'))!=(actual['document_id'],actual['version_id']):continue
            location=item.get('location',{})
            if item.get('quote')==gold['quote'] and location.get('line_start')==gold['line_start'] and location.get('line_end')==gold['line_end']:
                candidates.append(gold['evidence_id'])
        if len(candidates)==1:
            found.append(candidates[0])
            if item.get('source_integrity_verified') is False:invalid.append('source_integrity_invalid')
        else:invalid.append('unmapped_or_inexact_evidence')
    return found,invalid

def score(question,observed,manifest,mapping):
    reasons=[];expected=question['expected_response_category'];actual=observed['category']
    ids,invalid=map_evidence(observed.get('items',[]),manifest,mapping);reasons+=invalid
    if actual!=expected:reasons.append('response_category_mismatch')
    required=set(question['required_evidence_ids']);missing=required-set(ids)
    if missing:reasons.append('missing_required_evidence')
    forbidden={x['evidence_id'] for x in question['forbidden_evidence']}
    if forbidden.intersection(ids):reasons.append('forbidden_evidence_cited')
    body=observed.get('text','');text=normalized(body)
    relations={relation['relation_id']:relation for doc in manifest['documents'] for relation in doc['relations']}
    for relation_id in question['expected_relation_ids']:
        relation=relations[relation_id]
        if normalized(relation['predicate']+':') not in text or not set(relation['evidence_ids']).issubset(ids):reasons.append('missing_or_misbound_relation')
    if expected=='answer':
        for fact in question['expected_facts']:
            value=fact.rsplit(':',1)[-1].strip()
            # Source conditions must appear in the rendered answer or its exact supporting quote.
            condition_tokens=__import__('re').findall(r'요청 접수 후|\d+영업일|이내',value)
            matched=normalized(value) in text or (len(condition_tokens)>=3 and all(normalized(token) in text for token in condition_tokens))
            if not matched:
                reasons.append('missing_expected_fact');break
        citations=__import__('re').findall(r'\[(\d+)\]',body)
        if not citations or any(not 1<=int(x)<=len(observed.get('items',[])) for x in citations):reasons.append('citation_ordinal_invalid')
    elif observed.get('items'):reasons.append('unexpected_evidence')
    if expected=='deny' and observed.get('provider_calls_delta',0)!=0:reasons.append('provider_called_for_denied_resource')
    # Protected unique authored clauses must not occur in any returned payload.
    returned=observed.get('all_outputs','')
    by_id={x['evidence_id']:x for x in manifest['evidence']}
    for banned in question['forbidden_evidence']:
        if banned['enforcement_scope']=='all_outputs_and_provider_context' and by_id[banned['evidence_id']]['quote'] in returned:reasons.append('protected_clause_exposed')
    return {'question_id':question['question_id'],'classification':question['classification'],'scenario_id':question['scenario_id'],'actor_id':question['actor_id'],'tenant':question['active_tenant_id'],'mode':'mock','expected_category':expected,'actual_category':actual,'run_state':observed.get('state'),'http_status':observed['http_status'],'observed_evidence_ids':ids,'missing_evidence_ids':sorted(missing),'expected_relation_ids':question['expected_relation_ids'],'verdict':'fail' if reasons else 'pass','reasons':sorted(set(reasons)),'answer_sha256':digest(body.encode()),'provider_calls_delta':observed.get('provider_calls_delta',0),'verification_ids':question['verification_ids'],'requirements':question['requirements']}

def verify_index(db,manifest,mapping):
    """Read-only evaluator check after actual ingestion; gold never seeds runtime."""
    from common_core.ai_pipeline.graphrag.extractor import canonical
    entities={x['entity_id']:x for x in manifest['entities']};matched_evidence=set();matched_relations=set();coverage=[]
    with db.admin_connection() as conn:
        db.verify(conn)
        for doc in manifest['documents']:
            actual=mapping[(doc['document_id'],doc['version'])];raw=(ROOT/doc['source_path']).read_bytes();text=raw.decode('utf-8')
            rows=conn.execute('SELECT e.evidence_id,e.exact_quote,e.start_offset,e.end_offset,e.line_start,e.line_end,e.source_sha256 FROM rag.evidence e WHERE e.version_id=%s',(actual['version_id'],)).fetchall();by_actual={}
            for uid,quote,start,end,line_start,line_end,sha in rows:
                matches=[g for g in manifest['evidence'] if (g['document_id'],g['version'],g['quote'],g['line_start'],g['line_end'])==(doc['document_id'],doc['version'],quote,line_start,line_end)]
                assert len(matches)==1 and bytes(sha).hex()==doc['sha256'] and text[start:end]==quote
                by_actual[uid]=matches[0]['evidence_id'];matched_evidence.add(matches[0]['evidence_id'])
            relations=conn.execute('SELECT r.relation_id,r.relation_type,a.label,a.entity_type,b.label,b.entity_type FROM rag.relations r JOIN rag.entities a ON (a.tenant_id,a.index_id,a.entity_id)=(r.tenant_id,r.index_id,r.from_entity_id) JOIN rag.entities b ON (b.tenant_id,b.index_id,b.entity_id)=(r.tenant_id,r.index_id,r.to_entity_id) WHERE r.version_id=%s',(actual['version_id'],)).fetchall()
            for uid,predicate,left,lkind,right,rkind in relations:
                proofs={by_actual[x[0]] for x in conn.execute('SELECT evidence_id FROM rag.relation_evidence WHERE relation_id=%s',(uid,)).fetchall()}
                matches=[]
                for gold in doc['relations']:
                    ge_left=entities[gold['subject_entity_id']];ge_right=entities[gold['object_entity_id']]
                    if (predicate,canonical(lkind,left),canonical(rkind,right),proofs)==(gold['predicate'],canonical(ge_left['kind'],ge_left['label']),canonical(ge_right['kind'],ge_right['label']),set(gold['evidence_ids'])):matches.append(gold['relation_id'])
                assert len(matches)==1;matched_relations.add(matches[0])
            row=conn.execute('SELECT coverage FROM rag.index_builds WHERE index_id=%s',(actual['index_id'],)).fetchone();coverage.append({'document_alias':doc['document_id'],'version_alias':doc['version'],'coverage':row[0]})
    assert len(matched_evidence)==18 and len(matched_relations)==16
    return {'gold_evidence_matched':18,'gold_relations_matched':16,'source_exact_spans_verified':True,'relation_own_evidence_verified':True,'coverage':coverage}

class Api:
    def __init__(self,state):
        import httpx
        self.state=state;self.clients={};self.httpx=httpx
    def client(self,actor):
        if actor not in self.clients:
            client=self.httpx.Client(base_url='http://127.0.0.1:8000',timeout=10,trust_env=False)
            reply=client.post('/api/v1/auth/login',headers={'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'},json={'login_id':actor.lower(),'password':self.state.passwords[actor]})
            if reply.status_code!=200:raise RuntimeError('EVALUATOR_LOGIN_FAILED')
            self.clients[actor]=(client,reply.json()['data']['csrf_token'])
        return self.clients[actor]
    def request(self,actor,tenant,method,path,**kwargs):
        client,csrf=self.client(actor);headers={'X-Tenant-ID':str(self.state.tenant_ids[tenant])}
        if method!='GET':headers.update({'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf})
        return client.request(method,'/api/v1'+path,headers=headers,**kwargs)
    def data(self,actor,tenant,method,path,**kwargs):
        reply=self.request(actor,tenant,method,path,**kwargs)
        if reply.status_code not in (200,201,202):raise RuntimeError('EVALUATOR_API_'+str(reply.status_code))
        return reply.json()['data']
    def terminal(self,actor,tenant,path,key):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            data=self.data(actor,tenant,'GET',path)
            if data.get(key) or data.get('state') in ('completed','failed','needs_review','cancelled','interrupted'):return data
            time.sleep(.25)
        raise RuntimeError('EVALUATOR_TERMINAL_TIMEOUT')
    def close(self):
        for client,_ in self.clients.values():client.close()

def main():
    from scripts.devdb import DevCluster,_write_private,_read_private
    def save(path,text):
        if path.exists():_read_private(path);path.unlink()
        _write_private(path,text)
    from scripts.migrate import create_fixture_database,apply_migrations
    from scripts.seed import seed_fixture
    import httpx
    cluster=DevCluster();prior=cluster.status()['state'];db=None;state=None;api=None;process=None;log=None
    source_root=BACKEND/'.runtime'/('C06-source-'+uuid4().hex);started=time.monotonic();result={'stage':'C06','mode':'mock','paid_dispatches':0,'questions':[]};mapping={};private=[]
    def stop():
        nonlocal process
        if process:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            process=None
    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);probe.bind(('127.0.0.1',8000))
        if prior!='running':cluster.start()
        db=create_fixture_database();apply_migrations(db);state=seed_fixture(db)
        with db.admin_connection() as conn:
            db.verify(conn)
            for tenant in state.tenant_ids.values():
                conn.execute("INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) SELECT %s,budget_id,12500,12500 FROM ops.project_budget WHERE mode='mock'",(tenant,))
                conn.execute("UPDATE portal.agent_configs SET enabled=true,settings=%s WHERE tenant_id=%s AND agent_key='rules_rag'",(__import__('psycopg').types.json.Jsonb({'name':'규정 질문','description':'합성 자료 검증','instructions':'허용 근거에 따라 사실만 선택한다.'}),tenant))
        env={k:v for k,v in os.environ.items() if not k.startswith(('AI_','PG'))};env.update(AI_WEB_DSN=db.runtime_dsn(),AI_METER_DSN=db.runtime_dsn('ai_meter'),AI_INDEX_DSN=db.runtime_dsn('ai_index'),AI_LOGIN_HMAC_SECRET=__import__('secrets').token_urlsafe(32),AI_MODE='mock',AI_EXECUTION_ENABLED='true',AI_INDEX_ENABLED='true',AI_SOURCE_ROOT=str(source_root))
        log=os.fdopen(os.open(BACKEND/'.runtime/C06-native-private.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w')
        def start():
            nonlocal process
            process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8000','--no-proxy-headers','--no-access-log'],cwd=BACKEND,env=env,stdout=log,stderr=log)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError('EVALUATOR_NATIVE_START_FAILED')
                try:
                    if httpx.get('http://127.0.0.1:8000/api/v1/health',timeout=.3,trust_env=False).status_code==200:return
                except httpx.HTTPError:pass
                time.sleep(.1)
            raise RuntimeError('EVALUATOR_NATIVE_NOT_READY')
        start();api=Api(state);manifest=json.loads((ROOT/'data/synthetic/document_manifest.json').read_text());questions=json.loads((ROOT/'data/evaluation/questions.json').read_text())['questions'];grant=None
        for doc in manifest['documents']:
            raw=(ROOT/doc['source_path']).read_bytes();assert digest(raw)==doc['sha256'];tenant=doc['owner_tenant_id'];actor=tenant+'-ADM';meta={'client_upload_id':str(uuid4()),'title':doc['title'],'media_type':'text/markdown'};key=(doc['document_id'],doc['version'])
            if doc['version']=='v2':
                prior_doc=mapping[(doc['document_id'],'v1')];listing=api.data(actor,tenant,'GET','/admin/documents')['items'];meta['expected_revision']=next(x['revision'] for x in listing if x['document_id']==prior_doc['document_id']);path='/admin/documents/'+prior_doc['document_id']+'/versions'
            else:
                meta.update(visibility='private' if doc['scope']=='private' else 'org',reader_ids=[])
                if doc['owner_actor_id']:meta['owner_user_id']=str(state.actor_ids[doc['owner_actor_id']])
                path='/admin/documents'
            receipt=api.data(actor,tenant,'POST',path,files={'metadata':(None,json.dumps(meta),'application/json'),'file':('document.md',raw,'text/markdown')});job=api.terminal(actor,tenant,'/admin/jobs/'+receipt['job_id'],'terminal');assert job['state']=='completed',job['state'];mapping[key]=receipt
            if key==('D-S','v1'):
                grant=api.data('A-ADM','A','POST','/admin/documents/'+receipt['document_id']+'/versions/'+receipt['version_id']+'/grants',json={'recipient_tenant_id':str(state.tenant_ids['B']),'expected_publication_revision':1})
        def calls():
            with db.admin_connection() as conn:return conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]
        with db.admin_connection() as conn:
            result['ingestion']={'versions':conn.execute('SELECT count(*) FROM rag.document_versions').fetchone()[0],'jobs_completed':conn.execute("SELECT count(*) FROM rag.jobs WHERE state='completed'").fetchone()[0],'chunks':conn.execute('SELECT count(*) FROM rag.chunks').fetchone()[0],'entities':conn.execute('SELECT count(*) FROM rag.entities').fetchone()[0],'relations':conn.execute('SELECT count(*) FROM rag.relations').fetchone()[0],'evidence':conn.execute('SELECT count(*) FROM rag.evidence').fetchone()[0],'embedding_calls':calls(),'source_sha_verified':7}
        result['index_verification']=verify_index(db,manifest,mapping)
        old_source=None;old_run=None
        for question in questions:
            actor=question['actor_id'];tenant=question['active_tenant_id'];before=calls()
            if question['scenario_id']=='SHARE_REVOKED':
                api.data('A-ADM','A','DELETE','/admin/grants/'+grant['grant_id'],json={'expected_revision':grant['revision']})
            if question['request_fixture']['kind']=='direct_evidence_preview':
                assert old_source
                reply=api.request(actor,tenant,'GET',old_source.removeprefix('/api/v1'));view=api.data(actor,tenant,'GET','/runs/'+old_run);assert view['result'] is None and view['content_status']=='unavailable'
                observed={'category':'deny' if reply.status_code==404 else 'unexpected','http_status':reply.status_code,'all_outputs':reply.text,'items':[],'text':''}
            else:
                payload=runtime_payload(question,mapping);reply=api.request(actor,tenant,'POST','/runs',json=payload)
                if reply.status_code==404:observed={'category':'deny','http_status':404,'all_outputs':reply.text,'items':[],'text':''}
                elif reply.status_code in (200,202):
                    run=reply.json()['data']['run_id'];view=api.terminal(actor,tenant,'/runs/'+run,'is_terminal');proof=api.data(actor,tenant,'GET','/runs/'+run+'/evidence');body=(view.get('result') or {}).get('text','');
                    for item in proof['items']:
                        if item.get('content_status')!='available':continue
                        source=api.request(actor,tenant,'GET',item['source_url'].removeprefix('/api/v1'))
                        ref=next((doc for doc in manifest['documents'] if mapping[(doc['document_id'],doc['version'])]['version_id']==item['version_id']),None)
                        loc=item['location'];source_text=source.content.decode('utf-8') if source.status_code==200 else ''
                        item['source_integrity_verified']=bool(ref and source.status_code==200 and digest(source.content)==ref['sha256'] and source_text[loc['start_offset']:loc['end_offset']]==item['quote'] and source.headers.get('cache-control')=='no-store' and source.headers.get('x-content-type-options')=='nosniff')
                    category='answer' if view.get('answer_kind')=='answer' and view['state']=='completed' else 'hold' if view.get('answer_kind')=='insufficient_evidence' and view['state']=='completed' else 'failed'
                    observed={'category':category,'http_status':reply.status_code,'state':view['state'],'items':proof['items'],'text':body,'all_outputs':json.dumps({'view':view,'proof':proof},ensure_ascii=False)}
                    if question['question_id']=='Q-006' and proof['items']:
                        old_source=proof['items'][0]['source_url'];old_run=run;download=api.request(actor,tenant,'GET',old_source.removeprefix('/api/v1'));assert download.status_code==200;assert digest(download.content)==next(x['sha256'] for x in manifest['documents'] if x['document_id']=='D-S' and x['version']=='v1');result['shared_v1_source_sha_verified']=True
                    if question['question_id']=='Q-001':restart_actor,restart_tenant,restart_run,restart_payload,restart_view=actor,tenant,run,payload,view
                else:observed={'category':'failed','http_status':reply.status_code,'items':[],'text':'','all_outputs':reply.text}
            observed['provider_calls_delta']=calls()-before;result['questions'].append(score(question,observed,manifest,mapping));private.append({'question_id':question['question_id'],'observed':observed})
        before=calls();old_pid=process.pid;stop();start();restored=api.data(restart_actor,restart_tenant,'GET','/runs/'+restart_run);replayed=api.data(restart_actor,restart_tenant,'POST','/runs',json=restart_payload);assert restored['result']==restart_view['result'];assert replayed['run_id']==restart_run;assert calls()==before;result['restart']={'native':True,'health_ready':True,'pid_changed':process.pid!=old_pid,'completed_result_preserved':True,'same_send_id_same_run':True,'additional_calls':0}
        # Delete an organization document; direct refs must be rejected without a provider call.
        doc=mapping[('D-A-R1','v1')];listing=api.data('A-ADM','A','GET','/admin/documents')['items'];revision=next(x['revision'] for x in listing if x['document_id']==doc['document_id']);api.data('A-ADM','A','DELETE','/admin/documents/'+doc['document_id'],json={'expected_revision':revision});before=calls();denied=api.request('A-U1','A','POST','/runs',json={'agent_key':'rules_rag','client_send_id':str(uuid4()),'prompt':'가상 여신심사의 담당 부서는?','document_refs':[{k:doc[k] for k in ('document_id','version_id')}]});assert denied.status_code==404 and calls()==before
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            with db.admin_connection() as conn:remaining=conn.execute('SELECT count(*) FROM rag.chunks WHERE document_id=%s AND (NOT payload_purged OR text IS NOT NULL OR embedding IS NOT NULL)',(doc['document_id'],)).fetchone()[0]
            if remaining==0:break
            time.sleep(.1)
        assert remaining==0
        source_file=source_root/f"tenants/{state.tenant_ids['A']}/documents/{doc['document_id']}/{doc['version_id']}/source"
        assert not source_file.exists()
        result['deletion']={'direct_ref_status':404,'additional_calls':0,'derived_chunk_payload_removed':True,'identifier_history_retained':True,'source_file_removed':True}
        with db.admin_connection() as conn:
            result['calls']=[{'operation':o,'state':s,'count':n} for o,s,n in conn.execute('SELECT operation,state,count(*) FROM ops.call_attempts GROUP BY operation,state ORDER BY operation,state').fetchall()];result['budget']={k:str(x) for k,x in zip(('accounted_internal_krw','reserved_krw','active_slots'),conn.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone())}
        result['summary']={'executed':len(result['questions']),'passed':sum(x['verdict']=='pass' for x in result['questions']),'failed':sum(x['verdict']=='fail' for x in result['questions'])};save(BACKEND/'.runtime/C06-observations-private.json',json.dumps(private,ensure_ascii=False));return 0
    finally:
        if api:api.close()
        stop()
        if log:log.close()
        if db:
            with db.admin_connection() as conn:result['connections_after']=conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",(db.name,)).fetchone()[0]
            db.drop();result['fixture_removed']=True
        if state:state.secret_path.unlink(missing_ok=True)
        if source_root.exists():
            assert source_root.parent==BACKEND/'.runtime' and source_root.name.startswith('C06-source-');shutil.rmtree(source_root)
        if prior!='running':cluster.stop()
        result['cluster_after']=cluster.status()['state'];result['duration_seconds']=round(time.monotonic()-started,2);save(BACKEND/'.runtime/C06-evaluation-safe.json',json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        # Detailed exception belongs only in a private execution log.
        import traceback
        from scripts.devdb import _write_private
        path=BACKEND/'.runtime/C06-evaluator-error-private.txt'
        if path.exists():
            from scripts.devdb import _read_private
            _read_private(path);path.unlink()
        _write_private(path,traceback.format_exc())
        print(json.dumps({'error':type(error).__name__,'private_diagnostic_saved':True}));raise SystemExit(1)
