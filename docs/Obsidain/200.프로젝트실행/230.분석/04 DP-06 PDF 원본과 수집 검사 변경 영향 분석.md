# DP-06 PDF 원본과 수집 검사 변경 영향 분석

## 확인한 구조

현재 SourceStorage, common_core.parse_source와 build_document_plan은 UTF-8 TXT/Markdown을 전제한다. rag.document_versions의 media_type은 두 텍스트 형식만 허용하고 source_sha256은 저장된 텍스트 지문이다. source_mapping은 버전 등록 시 서버가 생성하며 변경 불가이고 내용 정리 때만 제거할 수 있다. 답변 봉인 함수는 증거 위치의 텍스트/행 오프셋을 DB 증거와 정확히 대조하므로 페이지 필드를 임의로 추가하면 기존 봉인이 실패한다.

## 방안 비교

| 방안 | 장점 | 비용/영향 |
|---|---|---|
| 원본 sidecar와 불변 source_mapping에 PDF 지문/페이지 기록 (채택) | 텍스트 DB·GraphRAG·증거 봉인 재사용; 다운로드만 원본 분기 | 두 파일 무결성·정리와 페이지 메타데이터 검증 필요 |
| 원본/추출물 전용 테이블 | 여러 형식 확장에 구조가 명확 | 이번 PDF 묶음에 RLS·권한·마이그레이션 범위 확대 |
| PDF를 텍스트로만 변환하고 원본 폐기 | 저장 구조 단순 | 원본 다운로드와 지문·페이지 추적 수용 기준 미충족 |

채택안은 기존 source 파일에 추출 텍스트를 저장하고 같은 버전의 original 파일에 PDF 원본을 보관한다. 원본 포맷/지문/길이/파서 버전/텍스트 지문/페이지 범위는 source_mapping.origin에 저장한다. source_sha256과 plan fingerprint의 기존 의미를 변경하지 않는다. 페이지 표시는 봉인된 텍스트 위치와 불변 페이지 맵으로 서버가 계산하고, 모델의 인용은 기존 봉인 계약을 유지한다.

## 선행 검사와 비용

기존 register는 파싱 후 같은 ID 영수증을 확인한다. 새 고정 함수024 document_upload_lookup은 현재 권한과 원본 기반 요청 지문을 확인하여 이미 확정된 재접수를 파싱 전에 반환한다. 새 요청은 분당10회 접수 제한을 파싱 전에 소비한다. 등록 커밋 시 기존 preflight도 다시 검사하여 동시 요청을 직렬화한다. 검사 실패는 할당된 접수 창만 소비하며 문서/색인/모델 호출을 만들지 않는다.

수집 정책은 app/policies/document_ingest.py에서 순수 함수로 제공한다. 원본 TXT/Markdown 및 제목, PDF 추출 전체 텍스트를 검사하고 worker 색인 전과 retrieval 문맥 구성 전 재확인한다. 일반 질문·모델 출력·도구 전반의 DP-18 정책은 후속이다.

## 의존성과 범위

pypdf6.19.0을 공식 배포의 SHA-256과 함께 고정한다. [공식 텍스트 추출 문서](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)는 큰 내용 스트림의 메모리 부담과 이미지 문서의 OCR 필요를 설명한다. [공식 라이선스](https://github.com/py-pdf/pypdf/blob/main/LICENSE)의 BSD 조건에 따라 의존 고지에 기록한다. 기본 패키지만 사용하고 암호 복호화/OCR 엔진은 도입하지 않는다. 공식 배포: https://pypi.org/project/pypdf/6.19.0/ . 설치 후 API와 실제 격리 제한을 시험한다.

원본·추출물의 물리 삭제와 원시 파일 경로는 사용자 이름/파일 이름에 의존하지 않는다. 다운로드는 기존 자료 권한·봉인된 답변·현재 조직 검사를 그대로 통과해야 한다. 기존 형식에는 원본 sidecar를 만들지 않는다.
