# AI 플랫폼 공통 문서·GraphRAG 코어

기존 GraphRAG의 파싱→청킹→Graph contracts/규칙 추출 책임 구조를 선택 참고해 이번 승인 명세에 맞게 재구현했다. 원본 실행 코드 그대로의 이식과 새 구현을 구분하며 파일 지문·보완은 provenance.json에 기록한다.

코어는 원문 bytes→parse_source→build_document_plan(metadata, injected tokenizer)의 순수 처리다. DB/HTTP/키/파일 읽기/사용자 권한 결정/provider 호출을 하지 않는다. 결과는 불변 객체이며 source/index context와 local ordinal을 보존한다. DB UUID·Job·게시·비용은 backend가 담당한다.

UTF-8 TXT/제한 Markdown, 128KiB/40,000 codepoint. source offset은 원본 Unicode 문자열 기준이다. 512 token/overlap0, 128chunk/512evidence/512entity/1024relation/2048edge, 8chunk/4096token/최대16batch를 사전 검사한다. 평가 정답/EV/R 목록은 코어 입력이 아니다. 일부 산출물을 잘라 완료 처리하지 않는다.

backend adapter는 기존 오프라인 cl100k_base 토큰 계산기를 주입한다. 테스트는 backend pyproject의 src module path로 import한다. native C03 서비스 연결 시 backend와 src를 모두 Python module path에 두어 표준 common_core import를 제공한다. 이 단계는 서비스 실행 설정을 변경하지 않는다.

파생 텍스트와 원본 quote를 분리한다. 비연속 mapping/잘린 문장은 관계를 확정하지 않는다. GR01~10의 긍정 문형/허용된 업무 alias만 적용하며 부정·조건 불명·값 충돌·미지원은 partial이다. 관계별 근거를 다시 추출해 대조하므로 단지 유효한 다른 quote를 붙이는 것도 거부한다.
