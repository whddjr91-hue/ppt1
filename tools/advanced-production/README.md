# 추가 제작 도구 연결

기존 `AGENTS.md`, 설정, 스킬, 1~5세션 역할을 바꾸지 않는 프로젝트 전용 추가 도구다. 이번에는 **PptxGenJS 엔진을 연결하라는 사용자 지정**을 적용했다. 기존 제작본과 원고를 재제작하지 않았다.

## 도구와 적용 범위

| 도구 | 고정 버전 | 역할 |
|---|---:|---|
| PptxGenJS | 4.0.1 | 새 PPTX 안에 네이티브 텍스트·도형·표·차트 생성 |
| Mermaid | 12.2.0 | 다이어그램 문법 검증과 노드·관계 추출 |
| jsdom | 26.1.0 | Node에서 Mermaid 한국어 라벨 sanitizer에 필요한 DOM 제공 |
| JSZip | 3.10.2 | 생성된 PPTX 패키지의 SVG PNG 미리보기만 교체 |
| sharp | 0.35.5 | SVG PNG 미리보기 생성. 프로젝트 전용 설치, 동버전 공유 런타임 선택 재사용 |

설치 위치는 이 폴더의 `node_modules`이며 전용 `package.json`/`package-lock.json`으로 고정한다. 기존 런타임에 PptxGenJS 4.0.1은 있었으나 Mermaid는 없었다. 재현 가능한 추가 설치를 위해 전용 패키지를 실제 설치했다. Node 22.12.0 이상이 필요하다. 캐시도 이 폴더의 `.npm-cache`에 두고 설치 스크립트·전역 설치·전역 설정 변경은 실행하지 않았다.

```bash
cd tools/advanced-production
npm ci --ignore-scripts --cache=.npm-cache
npm run diagnose
python3 scripts/verify-diagnostics.py
```

공식 출처·라이선스·설치 경로는 `sources.json`, 원문 라이선스 사본은 `licenses/`에 있다. 의존성의 원본 라이선스도 `node_modules`에 보존한다. 배포 시 해당 사용 조건을 유지한다.

## 기존 프로토와의 경계

**PptxGenJS는 기존 PPTX를 직접 import/edit하는 엔진이 아니다.** 기존 원본의 마스터·레이아웃·상속 객체·애니메이션·미디어를 보존하는 편집에는 기존 ppt-master의 native 편집/OOXML 경로를 우선한다. 이 추가 API는 새 네이티브 객체나 별도 새 파일을 만들 때 사용한다. 기존 원본에 새 객체를 병합하는 기능은 구현하지 않았다.

원본을 기준으로 만들 경우 먼저 실제 원본의 크기·색·글꼴·표·도형·화면/내레이션/제작지시 위치를 측정하고, 관련 페이지를 실제 렌더와 비교한다. 그런 다음 `proto`에 아래 값을 명시한다. 일반 발표형 기본값으로 바꾸지 않는다.

- `family`, `id`, `width`, `height`: 기관 구분과 원본의 실제 인치 규격.
- `font.face`, `font.bodyPt`, `font.titlePt`: 실제 원본 글꼴과 크기.
- `colors.background/ink/accent/frame`: 실제 원본에서 확인한 6자리 색상.
- `regions.header/content/narration`: 인치 단위 `x,y,w,h` 좌표.
- `reference.path/sha256`: 실제 원본 파일과 해시. production CLI는 파일을 읽어 해시가 맞는지 확인한다.
- 각 객체의 `box`/`placements`/`options`: 원본 위치·치수·세부 서식을 명시한다. 자동 레이아웃으로 원본을 대체하지 않는다.

샘플 2종은 `diagnosticOnly:true`인 **가상 KIRD/KEDI 진단 fixture**다. 실제 기관 양식·공식 프로토·역사학 완성본과의 동일성을 주장하지 않는다. 실무 프로필을 자동 추출하는 기능이나 원본 프로토의 모든 객체/상속 구조를 재현하는 기능은 없다.

## JavaScript API

```javascript
import {createNativeDeck} from './src/native-pptx.mjs';
const deck = createNativeDeck(measuredProto);
const slide = deck.addScene({
  title: approvedTitle,
  narration: approvedNarration,
  speaker: originalSpeaker,
  sceneId: 'SC001',
  cues: [{id:1, trigger:exactNarrationTrigger}],
  source: {paragraphId:'P01', memoIds:[]}
});
deck.text(slide, approvedKeywords, measuredTextBox);
deck.addTable(slide, approvedRows, measuredTableBox);
deck.addChart(slide, approvedSeries, measuredChartBox);
await deck.addMermaidNative(slide, structureSource, measuredNodePlacements);
await deck.save(newVersionedOutputPath);
```

`addScene`는 화자·원고·장면·싱크를 notes에 연결하며 원고를 자동 요약하거나 화자를 바꾸지 않는다. 각 페이지는 cue가 하나 이상 있어야 하고 ID는 1부터 연속이어야 한다. 내레이션의 첫 싱크 표식은 `#1`이어야 하며 모든 `#번호`에 대응하는 cue가 있어야 한다. 페이지마다 `#1`로 다시 시작하는 것은 허용한다. 부적합 입력은 원고를 자동 변경하지 않고 명시적으로 거부한다. 텍스트·도형·표·차트·SVG·Mermaid 노드의 좌표가 페이지 밖이면 실패한다. 이 범위 검사가 글자의 실제 잘림/겹침이나 원고 충실성을 증명하지는 않으므로 실제 렌더 검수는 별도다.

좌표 `x/y/w/h`는 검증하는 `box` 또는 `placements`에만 둔다. 텍스트·도형·표·차트의 `options`와 Mermaid의 `options.text`에 좌표 키를 넣으면 값과 관계없이 거부한다. CLI의 `op.options`에도 같은 검사를 적용한다. 좌표 옵션 우회 수정의 부정 입력 검사는 `node scripts/test-geometry-guards.mjs`로 실행하며 PPTX를 생성하지 않는다.

선언적 JSON 작업의 CLI도 제공한다.

```bash
npm run build -- /absolute/path/job.json /absolute/path/new-version.pptx
npm run mermaid -- /absolute/path/structure.mmd /absolute/path/structure.json
```

`job.json`은 `{proto, scenes:[{title,narration,speaker,sceneId,cues,source,objects:[]}]}` 구조다. 객체 type은 `text`, `shape`, `table`, `chart`, `svg`, `mermaid`이며 `scripts/build.mjs`의 매핑을 따른다. CLI는 기존 출력 파일을 덮어쓰지 않는다. 낮은 수준의 API는 신뢰할 수 있는 내부 측정 profile을 받는 용도다.

## Mermaid와 SVG

Mermaid는 **구조 설계/파싱**에 사용한다. 브라우저·Chromium·외부 CDN·렌더 우회는 사용하지 않는다. jsdom은 HTML 라벨 정화를 위한 DOM만 제공하고 외부 자원/스크립트 실행을 활성화하지 않는다.

현재 native 변환은 flowchart의 사각형/둥근사각형/마름모, 단순 방향 연결에 한정한다. 노드 위치는 항상 실제 프로토에 맞춘 `placements`를 받는다. 라벨 연결선에는 별도 라벨 좌표가 필요하다. Mermaid의 다른 다이어그램, HTML 라벨, subgraph, 클릭 동작/지시문과 비지원 도형/화살표는 실패한다. Mermaid 내부 DB 추출 API는 버전 의존성이 있어 고정 버전과 진단 테스트를 함께 유지한다. 자동 구조 추출이 최종 PPT의 스타일을 결정하지 않는다.

SVG는 작은 독립 이미지로 삽입하며 그림 내부 경로는 네이티브 편집 도형이 아니다. 최종 관계도·표·차트·문구는 각각 네이티브 객체로 유지한다. 슬라이드 전체를 이미지로 평탄화하지 않는다.

PptxGenJS 4.0.1의 Node 경로는 SVG를 보존하지만 PNG 미리보기를 깨진 그림으로 생성한다. `save()`는 그 PNG만 정확히 고정한 프로젝트 전용 `sharp` 0.35.5로 교체한다. `CODEX_PRIMARY_RUNTIME_NODE_MODULES`에 같은 버전이 있으면 선택적으로 읽기 재사용하고, 없거나 다른 버전이면 로컬 설치를 쓴다. `PPT1_SHARP_FORCE_LOCAL=1`로 로컬 경로를 강제할 수 있다. 이 방식은 기본 런타임 환경변수가 없는 컴퓨터에서도 로컬 설치로 동작한다. 미디어 이름 짝을 검증한 후 PNG만 교체하며 원본 SVG·네이티브 객체는 보존한다. 런타임 파일을 수정하거나 복사 설치하지 않았다.

## 실행 확인

`../../.local/advanced-tests/session3/`에 가상 양식별 2쪽, 총 4쪽 진단 PPTX/PDF/PNG를 생성했다. 실제 전4쪽을 열어 한글·표·차트·SVG·도형·페이지 싱크 및 잘림/겹침을 확인했다. CRC, 전체 XML 파싱, 내부 관계 대상, 각2쪽/정확 크기, 편집 가능한 표·차트, 차트값 `[2,4,3]`와 embedded workbook CRC, 원본 SVG/PNG 미리보기, Mermaid 페이지의 그림0개를 검사했다.

이는 기본 도구 연결 시험이다. 실제 PowerPoint 앱의 열기/편집/재저장, 원본 프로토 일치, 전체 문서의 실제 가독성, 오디오·애니메이션·모션/MP4 재생은 확인하지 않았다. 최종 품질·권리·기관감수·사용자 수용을 의미하지 않는다. 상세 판정은 `integration-result.json`이다.
