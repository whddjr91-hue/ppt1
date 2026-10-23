# 프로젝트 Playwright CLI 어댑터

기존 `.claude/skills/playwright-skill`과 사용자 `playwright-cli`를 보존한다. 공식 OpenAI 원본은 `vendor/skills/openai-playwright/`에 변경 없이 보관했다. 고정 commit과 9개 파일의 Git blob/SHA256은 `upstream-files.json`에 있다. Apache 2.0 원문과 Microsoft 파생 고지는 vendor의 `LICENSE.txt`·`NOTICE.txt`를 따른다.

기존 프로젝트 스킬은 JS 스크립트 작성 중심이고, CLI는 스냅샷에서 얻은 요소 ref를 명령 사이에 사용한다. 사용자에게 이미 있는 `playwright-cli`와 OpenAI 가이드는 이 핵심 기능이 겹친다. 자동 트리거를 중복 등록하지 않고 사용자 스킬을 우선한다. 이 추가의 이득은 공식 출처 고정과 프로젝트 실행 버전 고정이다.

어댑터는 `CODEX_PRIMARY_RUNTIME_NODE_MODULES`의 기존 Playwright **1.62.1**과 CLI 진입점 SHA256을 먼저 확인해 재사용한다. 일치하는 공유 런타임이 없으면 `tools/advanced-browser/node_modules`의 동일 버전을 사용할 수 있다. `npx @latest`나 전역 설치를 실행하지 않는다.

다른 컴퓨터에 일치하는 런타임이 없을 때만 이 폴더에 패키지를 설치한다. `package.json`의 정확한 `playwright: 1.62.1`과 공식 npm registry 기반 `package-lock.json`을 따른다. 아래 명령은 설치 스크립트를 실행하지 않으며 Chromium 바이너리를 내려받지 않는다. 기존 공유 런타임이 일치하면 이 설치를 생략한다.

```bash
npm ci --prefix tools/advanced-browser --ignore-scripts --no-audit --no-fund
```

이번 설정 작업에서는 `npm install --package-lock-only --ignore-scripts --registry=https://registry.npmjs.org --no-audit --no-fund`로 잠금 파일만 생성했다. 현재 `node_modules` 추가 설치·브라우저 재다운로드·실행 검증 확대는 하지 않았다. 공식 npm tarball 무결성과 CLI 진입점 해시 비교 근거는 `.local/advanced-tests/session4/npm-source-verification.json`에 기록한다.

```bash
node tools/advanced-browser/playwright-cli.cjs --runtime-info
node tools/advanced-browser/playwright-cli.cjs --version
node tools/advanced-browser/playwright-cli.cjs --help
node tools/advanced-browser/smoke.cjs --preflight
```

브라우저가 없을 때만 명시적으로 실행할 설치 옵션이다. Playwright가 제공하는 Chromium headless shell만 프로젝트 `.local/advanced-browser-cache`에 설치하며 시스템 패키지·전역 npm은 변경하지 않는다.

```bash
node tools/advanced-browser/playwright-cli.cjs --install-browser
node tools/advanced-browser/smoke.cjs
```

headless shell만 설치한 환경에서 CLI가 전체 Chromium을 찾는다면 `PPT1_PLAYWRIGHT_EXECUTABLE_PATH`로 실제 설치된 실행 파일을 지정할 수 있다. 임의의 내부 registry 경로를 가져오거나 실행 파일 경로를 추측하지 않는다. 기본 경로 확인에는 공개 `chromium.executablePath()` API를 쓰고 실제 headless 선택은 Playwright에 맡긴다.

로컬 smoke는 임시 localhost 페이지와 새 격리 CLI 세션을 사용한다. 스냅샷의 실제 ref로 버튼을 누른 뒤 스냅샷·스크린샷을 저장한다. 테스트 기록은 `.local/advanced-tests/session4/`에 남긴다. 사용자 CDP·브라우저 확장·인증 저장소에 연결하지 않는다.

현재 환경에서는 공식 Chromium CDN이 ZIP 대신 `Site Unavailable` HTML을 반환했다. CLI 버전·도움말·명령 파서·공개 API preflight는 통과했으나 실제 브라우저 열기는 미설치 오류로 실패했다. 스냅샷과 스크린샷은 생성되지 않았다. 차단 우회나 다운로드 재시도는 하지 않았다.

외부 서비스 작업에는 해당 서비스 플러그인을 우선한다. 이 어댑터 설치가 브라우저 사용·계정 접근·차단 우회를 추가 허가하지 않는다. PDF 작업은 기존 PDF 스킬의 렌더·내용 검수를 사용하고, 브라우저 페이지 PDF 출력은 필요한 경우 별도 보조 산출물로만 취급한다.
