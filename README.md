# AI 플랫폼 개인 학습·MVP

문서는 `docs/Obsidain`의 프로젝트 단계별 폴더에서 관리합니다. 코드는 `src/frontend`, `src/backend`, `src/common_core`에 둡니다.

2026-10-05 기준 A 인증·테넌트·권한과 B01~05 대화 저장·운영 API·AI 실행 제어·사용자/관리자 화면을 구현하고 검증했습니다. 일반 질문·실시간 초안·저장 재조회·취소, Agent 설정·본인/조직 사용량·한도·독립 플랫폼 운영 화면을 제공합니다. 27 API/16업무 테이블/9 migration, backend477 pass·기존A20+새B31=browser51 pass/build 성공입니다. 실제 OpenAI 호출0건/0원입니다.

기본 합성 A/B 환경의 누락 mock 예산과 일반 Agent, 비공개 실행 설정을 준비했습니다. 등록된 API 키·web DSN·인증 HMAC·기존 대화·real 예산은 보존했습니다. 준비 명령 재실행 추가 변경0이며 기발생 사용·예약을 초기화하지 않습니다. 서버를 실행하면 모의 대화를 시연할 수 있습니다. 현재 서버/DB는 정지 상태입니다. 실제 OpenAI 대표3회는 B06, GraphRAG와 문서 검색·Q20은 C 후속 작업입니다.

[현재 구현 결과](docs/Obsidain/200.프로젝트실행/250.구현/04%20일반%20대화와%20중앙%20AI%20구현%20결과.md) · [B05 상세 작업](docs/Obsidain/200.프로젝트실행/250.구현/07%20대화와%20운영%20화면%20상세%20작업%20계획.md) · [backend 실행 안내](src/backend/README.md) · [frontend 실행 안내](src/frontend/README.md) · [검증 증거](docs/Obsidain/200.프로젝트실행/260.테스트/evidence/B-chat/README.md)
