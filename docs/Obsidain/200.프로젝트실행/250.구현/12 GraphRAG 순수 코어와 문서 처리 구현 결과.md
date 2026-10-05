---
title: GraphRAG 순수 코어와 문서 처리 구현 결과
created: 2026-10-05
updated: 2026-10-05
status: completed
stage: 250.구현
tags: [implementation-result, C02, graphrag, provenance]
---

# I250-C02 구현 결과

C02를 완료했다. 원본 GraphRAG의 처리 책임 구조를 참고해 `src/common_core`에 순수 처리 모듈을 구현하고, backend에 오프라인 토큰 계산기를 주입하는 adapter를 연결했다. 실제 문서 등록·인덱싱 실행·임베딩·검색·RAG 응답은 아직 연결하지 않았다.

## 구현 범위

- 원문 SHA와 원본 Unicode offset/행 번호를 유지하는 UTF-8 TXT·제한 Markdown 파서. BOM/CRLF/반복 문장을 위치 추측 없이 처리한다. 시작 frontmatter·합성 고지·HTML anchor·EV ID를 처리 입력에서 제외한다.
- 문장 경계 우선 512토큰/overlap0 청킹, 청크8개·4096토큰/최대16배치 계획. 긴 문장은 문자 경계에서 나누고, 잘린 주장으로 관계를 확정하지 않는다. 승인된 청크/근거/Graph 상한 초과는 provider 호출 전에 거부한다.
- GR01~10 제한 긍정 문형과 6개 개체 유형의 방향·조건·상대 기한을 보존한다. 관계별 실제 연속 quote만 연결한다. 비연속 Markdown 원문 조각·부정·대명사 불명·값 충돌·미지원은 부분 처리다. 적용 범위가 불명한 예외가 있으면 문서 관계 전체를 보류하는 보수적 정책을 사용한다.
- tenant/document/version/index/source/mode/parser/pipeline/model/dimension을 불변 scope와 fingerprint에 바인딩한다. 유효한 다른 quote를 잘못 붙이는 경우도 규칙 재추출 대조로 거부한다. 모드·index가 다른 결과의 재사용을 거부한다.
- 코어는 DB/HTTP/키/파일 읽기/provider를 의존하지 않는다. backend adapter만 기존 검증된 오프라인 cl100k_base tokenizer를 주입한다. pytest src 경로를 추가했고 native 서비스 경로는 C03에서 연결한다.

## 기존 GraphRAG 활용

원본 HEAD `913f3881b4a4a73b9f764f60575775ecdbba6bdd`와 검토 소스9개의 SHA를 확인했다. DocumentPipeline/ParserRegistry/Chunker/Graph schema/RelationExtractor의 책임과 인터페이스를 참고한 새 구현이며 그대로 복사한 소스 파일은 0개다. 문자 수 청킹·원문 find 위치 추정·keyword cross-product 관계 생성을 이번 명세대로 보완했다. 확인한 root/pyproject에는 명시적 LICENSE/NOTICE 또는 프로젝트 license 선언이 없어 미확인으로 기록하고 임의 license를 만들지 않았다. 원본을 실행하거나 수정하지 않았다. 상세는 `src/common_core/provenance.json`과 README에 기록한다.

## 검증 결과

관련 **72개 통과 / 실패0 / 1.17초**, 전체 backend **671개 통과 / 실패0 / 666.48초**. 관련 시험은 전체에 포함하므로 합산하지 않는다. 전체 경고0을 확인했으며 경고 억제를 추가하지 않았다. frontend/route/서비스 설정 변경이 없어 이 단계의 browser 재실행은 하지 않았다. C01 browser51 통과는 이전 단계의 결과다.

처음 import 실패를 확인한 뒤 구현했다. 첫 구현 시험은60통과/2실패였다. 근거512개 상한을 넘었던 반복문 시험 입력을 유효 범위로 조정하고, 조건이 붙은 점검표 문형의 조건 capture를 수정했다. 불명한 예외의 주장 보류를 추가해64개 통과, 원문7버전 평가 분리 시험을 추가한 최종72개가 통과했다. 오류를 숨기거나 시험 기대값으로 runtime 관계를 생성하지 않았다.

| 실제 원문 처리 계획 | 결과 |
|---|---:|
| 원문 버전 | 7 |
| 청크 | 7 |
| 개체 | 23 |
| 원문 근거 | 18 |
| 관계 | 16 |
| 임베딩 배치 계획 | 7 |
| 오프라인 임베딩 토큰 계획 합계 | 819 |
| 규칙 complete / partial 문서 | 5 / 2 |
| 실제 임베딩·영구 index 저장 | 0 / 0 |

7개 입력은 원문 bytes/제목/등록 metadata만 사용했다. 처리 후 별도 evaluator가 기존 정답16관계·18근거의 값/quote/행/offset을 대조했다. partial2개는 미지원 문장을 근거로 보존하며 관계를 추정하지 않는다. 이 결과는 작은 합성 corpus와 제한 문형의 검증이며 임의 금융 문서 추출 품질·검색 정답률을 보장하지 않는다. Q20는 not_run, 평가 원본과 authored_static_validated_not_loaded 상태는 보존한다.

## 보존과 현재 상태

SQL/primary/키/기존 사용량을 변경하지 않았다. 새 의존성·유료 발사·추가 비용은0이다. 기존 실제 일반 AI3회와 내부 추정0.19원은 그대로 보존하며 공급자 청구 확인값으로 표현하지 않는다. 기본 mock·RAG 비활성, 현재31업무모델/infra1·11migration·49security함수·27API는 C01 상태 그대로다. 최종 보존 수량·종료 상태는 `C02-preservation.json`에 기록한다.

개인 실제 학습·개발 투입 시간은 미측정이다. C02 예상3h는 기존 C20h 배분 안의 계획이며 자동 시험 경과와 구분한다. 10월31일·주20시간 이상/80h(여유10h포함) 기준을 유지한다. 전체 진행률을 임의 %로 추정하지 않는다.

## 다음 C03

[[13 문서 등록과 인덱싱 Job 상세 작업 계획]]의 예상4h: 실행 경로·최소 인덱서/새 migration30분 → 등록 receipt·원문 보상40분 → Job lease/epoch45분 → 중앙 임베딩·비용/checkpoint50분 → 원자 게시·삭제cleanup40분 → 실제DB/재시작/회귀·C04계획35분. 완료 기준은 동일ID1접수·unknown 자동 유료 재발사0·현재권한 회수/삭제 차단·실패 시 이전 게시본 유지다. C03는 계획이며 이번 작업에서 실행하지 않았다.

근거: [[../260.테스트/evidence/C-rag/C02-README]], [[11 GraphRAG 순수 코어와 문서 처리 상세 작업 계획]], [[09 문서와 GraphRAG 연결 상세 작업 계획]].

C02 실제 검증 소스 local commit: `d54f2a18e662d04e27c4c0ff1af430fbe6abe656`. 정확 36개 변경 파일만 기록하고 시험 소스 83개 SHA를 대조해 증거와 연결했다. 원격 push/배포 없음.
