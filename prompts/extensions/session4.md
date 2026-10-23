# 4세션 고급 도구 추가 지침

기존 자료·출처 담당과 code-first playwright-skill을 유지한다. `advanced-tools.json`과 `docs/고급도구추가.md`를 읽는다. CLI·snapshot ref 작업은 현재 playwright-cli 스킬과 프로젝트 고정 어댑터를 사용하고 공식 원본은 `vendor/skills/openai-playwright/SKILL.md`에서 확인한다. 동일 기능의 두 번째 자동등록이나 npx latest 설치를 반복하지 않는다. 서비스별 plugin을 우선하며 브라우저 사용·로그인·사이트 차단 정책을 따른다. snapshot 전후 상태 확인, 실제 캡처 경로, 원본 URL/ID·작가·권리·워터마크·원본→삽입 해시를 남긴다. PDF 자료는 내장 PDF 스킬로 텍스트와 페이지 이미지를 함께 확인한다. 브라우저 실행·캡처를 하지 못했으면 CLI 설치만으로 성공이라 하지 않는다.
