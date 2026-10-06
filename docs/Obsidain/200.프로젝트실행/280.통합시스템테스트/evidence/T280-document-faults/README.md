# T280 문서 장애 보완 증거

신규7개×3회/관련서버60개/전체화면63개를구분한다. counts는합산하지않는다.

- reproduction: 삭제 정리 제한 우회의 두 순서 실패/수정.
- regression-cases/fault-repetitions: 실제API·PG/RLS/원장·native재시작의 최종 사례별 결과.
- verification-matrix: 최신143하위조건16pass/127not_run,상위2pass/39not_run. 전체41개 완료 아님.
- source-fingerprints: 실제 소스174개 지문. 전체174개가이번관련시험으로각각실행됐다는뜻은아님.
- real-readiness/preservation: 기존1차증거/키·원장·배정/자료보존,실RAG not_run.

관련 이전 증거는 ../T280-integration/ 또는기존C06 원본을참조한다. 기존결과를덮어쓰지않는다. 원문·키·DSN·비공개로그는여기에넣지않는다. 삭제 정리 장애는임시version디렉터리의경로보호오류이며모든unlink I/O장애유형에대한검증아님이다.
