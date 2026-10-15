---
title: 기존 화면 검토와 MVP 범위
created: 2026-10-04
updated: 2026-10-04
status: review-draft
purpose: 개인 AI 통합 포털 학습·MVP
tags:
  - ai-portal
  - learning
  - mvp
---

# 기존 화면 검토와 MVP 범위

> [!important] 2026-10-04 프로젝트 기준 정정
> 현재 학습·MVP 대상은 **BNK 그룹 공동 생성형 AI 플랫폼**이다. [[개발/AI 통합 포털/05 BNK 플랫폼 기준 정정과 개인 MVP]]를 우선한다. 이 문서의 이전 화면/도메인/범위 판단은 해당 자료에 한정하며 새 플랫폼의 요구범위로 자동 적용하지 않는다.

## 실제 확인한 상태

제공 폴더의 HTML 21개를 파일·텍스트·스크립트 기준으로 검토했고 User-home과 준법 관리자 대시보드는 브라우저에서 확인했다. 전체 화면에 대해 모든 버튼을 시험한 것은 아니다.

User-home은 채팅·문서함·마켓플레이스·관리자 뷰를 한 HTML에 포함한다. 응답은 CHAT_CONTENT·프리셋·matchResponse 등 준비된 문구를 보여준다. 조사한 HTML에서 fetch/XMLHttpRequest/WebSocket/EventSource 및 localStorage/sessionStorage 호출을 찾지 못했다. 따라서 제공 파일만으로 실제 인증·DB 저장·모델 호출·지식 검색·통계 수집을 구현했다고 볼 수 없다.

다른 화면은 AI 서비스 등록→위험등급→기획→개발→검증→운영의 **거버넌스 관리 화면**이다. 포털 사용자·모델·비용을 관리하는 **플랫폼 운영 관리자**와 역할이 다르다. 둘은 나중에 서비스 ID로 연결할 수 있다. ‘위험등급·법 적용·연 1회 모니터링’ 문구는 기존 시연 내용으로만 분석했으며 법적 준수 기준으로 확인하지 않았다.

## 화면을 MVP 기능으로 연결

| 기존 요소 | M1에서 활용 | 새로 필요한 실제 동작 | 이후 |
|---|---|---|---|
| 채팅 입력·전송·답변·기록 | 우선 활용 | 서버 모델 호출·스트리밍·저장·본인 조회·실패 표시 | 파일 첨부·고급 메시지 형식 |
| 모델 선택 | 허용 모델 1개 표시 | 서버 allowlist·모델 별칭·설정 | 모델 2개·교체 |
| 문서작성 바로가기 | ‘문서 요약’ 프롬프트 | 승인된 템플릿 버전·제한된 입력 | 서비스별 템플릿 확장 |
| 문서함·AI 문서 참조·Sources | M2 | 업로드·인덱스 상태·검색·근거·원본 권한 | PDF·표·OCR 등 포맷 확장 |
| 관리자 탭 | 위치·메뉴 활용 | 사용자·모델·한도·사용량·오류·중지 | 조직별 정책 |
| 마켓플레이스·My Agent | M3 카드 목록 활용 | 실제 서비스 등록·승인·실행권한 | Agent·Workflow·MCP 유형 |
| 서비스 등록·목록·상세 | M3 기본정보 일부 | owner·목적·모델·프롬프트·상태·버전 | 생애주기별 상세 증빙 |
| 위험등급·기획·개발·검증·운영 | 별도 후속 과제 | 상태전이·결재·증빙·검토 기준 | 도메인 전문가와 범위 확정 |
| 준법 대시보드 | 차트·표 표현 참고 | 플랫폼용 실제 호출·사용량 통계로 재정의 | 준법 지표는 별도 자료 기반 |
| 회의 오디오·회의록 | 보류 | 음성 전사·저장·동의·실제 처리 | 별도 서비스로 확장 |
| 커뮤니티·지식공유·자산 평가 | 보류 | 사용자 콘텐츠·권한·검색·관리 | 핵심 MVP 이후 |

## M1 화면 5개와 최소 기능

1. 로그인: 사용자 A/B, 관리자 C. 역할 선택만으로 권한을 바꾸는 데모와 실제 인증은 구분한다.
2. 채팅: 질문·실제 답변·생성 중·중지·오류·프롬프트 2개.
3. 기록: 대화 목록·다시 열기·본인 자료만 조회.
4. 관리자 설정: 사용자 활성/중지, 허용 모델, 사용자 요청 제한, 서비스 중지.
5. 관리자 현황: 호출수·성공/실패·입출력 토큰·응답시간·추정비용·오류 유형.

각 화면은 화면 수가 아니라 같은 요청을 통해 연결되는 것으로 완료를 판정한다. 기존 표시 수치 1,284명·239개 자산·3,402대화 등은 샘플이므로 초기화하고 실제 데이터로 집계한다.

## M1 완료 시연

사용자 A 로그인→승인 프롬프트 실행→AI 답변 수신→기록 재조회→사용자 B로 A의 대화 조회 거부→관리자로 토큰/응답시간 확인→사용자 A 제한 또는 서비스 중지→A의 다음 요청이 제공자 호출 전에 차단되는 흐름을 실행한다.

모의 모델 모드는 화면에 표시한다. 실제 모델 모드에서는 제공자 응답·모델·usage 출처를 기록한다. 두 모드의 성공 건수와 비용을 혼합하지 않는다.

## 원본 관리

원본 HTML은 보존하고 구현 프로젝트의 화면으로 복사·분리한다. 여러 HTML의 등록·미등록·조회 상태는 별개 앱이 아니라 하나의 데이터 상태로 구현한다. 개발 v0.7/v0.8은 대조 후 대표 화면을 고른다. 더 큰 버전 번호가 항상 기능 일관성이나 검증 완료를 뜻하지 않는다.

User-home이 참조하는 Chatbot.png가 제공 폴더에 없어 브라우저에서 이미지가 깨진다. 대시보드 등의 링크 파일명 정규화(NFC/NFD)와 사고 목록 파일 누락도 연결 단계에서 확인해야 한다. 기본정보 탭 진행 상태와 우측 서비스 현황의 운영 상태가 서로 다른 샘플도 있어, 구현 시 실제 상태값 하나로 표시를 통일한다.

## 파일 목록

아래 이름은 표시 편의를 위해 한글 조합형으로 정규화했다. 실제 원본 경로는 제공 폴더의 파일명을 따른다.

| 원본 | 분류 | 대응 |
|---|---|---|
| [BNK_AI_Compliance_개발_v0.7.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_개발_v0.7.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_개발_v0.8.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_개발_v0.8.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_개발_등록_v0.7.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_개발_등록_v0.7.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_개발_미등록_v0.3.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_개발_미등록_v0.3.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_검증_v0.64.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_검증_v0.64.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_검증_등록_v0.7.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_검증_등록_v0.7.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_검증_미등록_v0.3.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_검증_미등록_v0.3.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_기획_v0.5.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_기획_v0.5.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_기획_등록_v0.5.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_기획_등록_v0.5.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_기획_미등록_v0.3.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_기획_미등록_v0.3.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_대시보드_v0.2.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_대시보드_v0.2.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_서비스_등록_v0.4.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_서비스_등록_v0.4.html>) | 서비스 기본 관리 | M3 축소 활용 |
| [BNK_AI_Compliance_서비스_목록_v0.8.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_서비스_목록_v0.8.html>) | 서비스 기본 관리 | M3 축소 활용 |
| [BNK_AI_Compliance_서비스_상세정보_v0.7.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_서비스_상세정보_v0.7.html>) | 서비스 기본 관리 | M3 축소 활용 |
| [BNK_AI_Compliance_운영_v0.5.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_운영_v0.5.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_운영_등록_v0.4.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_운영_등록_v0.4.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_운영_미등록_v0.3.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_운영_미등록_v0.3.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_위험등급_v0.5.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_위험등급_v0.5.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_위험등급_등록_v0.3.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_위험등급_등록_v0.3.html>) | 거버넌스·생애주기 | 후속 과제 |
| [BNK_AI_Compliance_위험등급_미등록_v0.3.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/BNK_AI_Compliance_위험등급_미등록_v0.3.html>) | 거버넌스·생애주기 | 후속 과제 |
| [User-home.html](</Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/BNK_AI_Compliance_화면_전체/User-home.html>) | 사용자·플랫폼 관리자 | M1 핵심 / M2 문서 / M3 자산 |
