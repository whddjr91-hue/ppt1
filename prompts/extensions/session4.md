# 4세션 고급 도구 추가 지침

기존 자료·출처 담당과 code-first playwright-skill을 유지한다. 해당 고급 도구를 사용할 때 `advanced-tools.json`과 `docs/고급도구추가.md`의 관련 절을 확인한다. CLI·snapshot ref 작업은 현재 playwright-cli 스킬과 프로젝트 고정 어댑터를 사용하고 공식 원본은 `vendor/skills/openai-playwright/SKILL.md`에서 확인한다. 동일 기능의 두 번째 자동등록이나 npx latest 설치를 반복하지 않는다. 서비스별 plugin을 우선하며 브라우저 사용·로그인·사이트 차단 정책을 따른다. snapshot 전후 상태 확인, 실제 캡처 경로, 원본 URL/ID·작가·권리·워터마크·원본→삽입 해시를 남긴다. PDF 자료는 내장 PDF 스킬로 텍스트와 페이지 이미지를 함께 확인한다. 브라우저 실행·캡처를 하지 못했으면 CLI 설치만으로 성공이라 하지 않는다.

Chromium 153 설치 후 로컬 캡처 검증을 통과했다. CLI daemon이 Unix socket EPERM으로 막힌 환경은 `node tools/advanced-browser/capture.cjs <URL> <출력.png>`의 공식 API 경로를 쓴다. 설치·해시 검증·적용 한계는 `tools/advanced-browser/README.md`를 따른다. 기존 CLI와 code-first 스킬은 보존한다.

실행·모델·캐시·부분 수정 범위는 `docs/작업범위와재사용.md`를 참조한다. 이 역할이 선택되지 않았으면 사전 분석이나 대기용 호출을 생성하지 않는다.
