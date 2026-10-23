# 프로젝트 Playwright·Chromium 캡처

기존 `.claude/skills/playwright-skill`, 사용자 `playwright-cli`, 공식 원본 `vendor/skills/openai-playwright/`를 보존한다. 동일 generic 스킬을 다시 등록하지 않는다. Playwright 1.62.1과 CLI SHA256은 runtime-lock.json에 고정해 기존 공유 런타임을 재사용한다. 같은 버전이 없을 때만 이 폴더의 package-lock.json으로 설치한다.

```bash
node tools/advanced-browser/playwright-cli.cjs --runtime-info
# 일치하는 공유 런타임이 없을 때만:
npm ci --prefix tools/advanced-browser --ignore-scripts --no-audit --no-fund
```

## 추가 설치 완료

사용자 요청으로 Chromium을 추가했다. 공식 CDN의 Chrome Headless Shell151 ZIP은 정상 파일이 아니어서 설치에 실패했다. 별도 npm 배포본 `@sparticuz/chromium@153.0.0`의 archive SHA512를 고정해 설치했으며 실제 버전은 **Chromium153.0.8010.0**이다. Linux x64, Node ^22.17.0 또는 >=24.0.0을 요구한다. MIT 패키지·Chromium BSD 고지는 chromium/LICENSE, CHROMIUM-LICENSE, NOTICE.md에 있다.

```bash
# 새 컴퓨터에서 이 추가 의존성이 없을 때만:
npm ci --prefix tools/advanced-browser/chromium --ignore-scripts --no-audit --no-fund
node tools/advanced-browser/prepare-chromium.cjs
node tools/advanced-browser/smoke-api.cjs
node tools/advanced-browser/capture.cjs https://example.com /absolute/output.png
```

`capture.cjs`는 새 격리 브라우저에서 HTTP(S) 페이지를 열어 전체 페이지 PNG, 접근성 snapshot YAML, URL·제목·버전·확인시각 JSON을 저장한다. 로그인 상태와 사용자 브라우저는 연결하지 않는다. 자료의 출처·권리 판단은 기존 4세션 기준을 따른다. 서비스 플러그인이 있으면 플러그인을 우선한다.

압축 패키지는 `tools/advanced-browser/chromium/node_modules/@sparticuz/chromium`, 실행 파일은 같은 node_modules/.cache/ppt1-chromium 아래다. 경로·SHA256 영수증은 `.local/advanced-browser-cache/chromium-install.json`에 있다. 209,022,176바이트 및 SHA256을 준비·실행 시 검증한다. 큰 실행 파일을 소스 동기화 경로에 놓았을 때 잘린 현상을 확인해 생성 의존성 캐시로 분리했다. 손상 파일은 실행하지 않으며 prepare 명령으로 정상 로컬 원본에서 복구한다. 바이너리·node_modules·인증정보는 GitHub에 올리지 않는다.

## 검증과 제한

실제 localhost 페이지 열기→접근성 스냅샷→버튼 클릭→변경된 스냅샷→PNG 저장을 통과했다. 한국어 화면을 시각 검수했고 실행 전후 해시가 일치했다. 결과는 `tests/chromium-results.json`, 세부 로컬 근거는 `.local/advanced-tests/session4/api/`다. 외부 사이트별 접근 가능성·자료 사용권을 보장하는 시험은 아니다.

기존 CLI daemon은 이 환경에서 Unix socket listen EPERM으로 실행할 수 없다. CLI를 변경하거나 권한 제한을 해제하지 않았으며 공식 Playwright API stdio 전송을 사용하는 `capture.cjs`를 제공한다. 기존 `smoke.cjs`는 CLI 전용 진단으로 남겨 두었다. Chromium153은 공식 Playwright 기본151과 다르므로 고급 기능은 필요 시 추가 검증한다. root 컨테이너에서는 Chromium sandbox를 비활성화해야 실행되며, 일반 사용자에서는 활성화한다. 웹 보안·사이트 격리·인증서 검증을 해제하는 옵션은 추가하지 않았다.
