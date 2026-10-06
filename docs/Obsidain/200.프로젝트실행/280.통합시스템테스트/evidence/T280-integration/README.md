# T280 1차 통합 검증 증거

현재 단계는 진행 중이다. manifest의범위/소스/완료·미완료를기준으로확인한다.

- regression-cases: 수정 후관련 서버34개/전체화면63개. 전체backend새시험 아님.
- ordering-repetitions: 최종 순서8개×3회. critical-repetitions-before-fix: 수정 전97개×3회. 중복 합산하지 않는다.
- scheduler-reproduction: 실제결함의 기대/실패/수정/최종순서검증과별도의시험준비오류.
- performance/environment: 로컬Mock 200측정표본/워밍27개, 실제 API·PG/RLS·같은DB 재시작. 실제모델/SLA/새환경설치 증거 아님.
- verification-matrix: V41/ACL16/설계60·143하위조건, 독립대조11pass/132not_run. 관련모듈근거와전체최종판정을구분.
- static-audit: SDK AST허용경로·현재빌드/로그등록비밀값검사. 보호본문/제목표식전체주입은후속.
- real-readiness/preservation: 기존500대표배정/기발생0.19/비밀·자료/원본GraphRAG 보존, 실제RAG not_run.

측정 재현은backend의기존venv에서 `python -m scripts.t280_measure`를사용한다. 키없이별도표식폐기용DB만소유하고정리하며, 기존primary를초기화하지않는다. 동시에다른API/DB 시험을실행하지않는다. 이미수행된측정을다시실행해야할필요가있는경우에만사용한다. 비공개 원문/키/DSN/계정/오류로그는 이폴더에 저장하지 않는다.
