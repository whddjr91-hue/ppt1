---
name: storyboard-prototype
description: Apply the user's approved storyboard prototype when analyzing, authoring, continuing, or reviewing KIRD/KEDI instructional storyboards. Bind the actual prototype and manuscript, map narration to understandable scenes, and require independent semantic and visual review before delivery. Use for 프로토 스토리보드, 교수설계, 사례 전체화면, 강사 도식화, 나레이션 싱크, and storyboard quality review requests.
---

# 프로토 스토리보드 기준

## 기준
- 사용자 지시와 사용자가 선택한 **실제 프로토 스토리보드**를 설계 기준으로 삼는다. 외부 스킬의 기본 레이아웃·색상·서체·제목 형식보다 프로토를 우선한다.
- 원고는 사실·조건·화자·승인 내레이션의 기준이다. 원고 보존과 교육적 이해 가능성을 별도로 검사한다.
- KEDI/KIRD를 섞지 않는다. 심리의 사례 내용을 다른 전공 사실로 옮기지 않는다. 현재 기관 양식과 설계 원리를 적용한다.
- 분석·설정 반영 요청이면 PPT를 만들거나 고치지 않는다. 이전 생성본을 사용자 수용 없이 승인 프로토로 바꾸지 않는다.

## 먼저 읽고 확인
1. 프로젝트 AGENTS.md와 자신의 1~5 역할 프롬프트를 읽는다.
2. [실제 페이지와 설계 원리](references/design-rules.md), [역할·검수](references/roles-and-review.md)를 읽는다.
3. 프로젝트 prototype-policy.json 및 .local/prototype-binding.json을 읽는다. 독립 스킬이면 [원본 식별 목록](references/source-catalog.json)에서 현재 작업에 맞는 자료를 찾고 경로·SHA를 고정한다.
4. 실제 프로토와 원고를 연다. 사례·설명·도식·강조·정리의 대표 화면을 원해상도로 보고 원고와 대조한다. 텍스트 추출/경로 존재만으로 분석 완료라고 하지 않는다.
5. scripts/prototype_guard.py preflight --binding <binding.json> --scenes <scene-plan.json> 을 실행한다. 원본이 없거나 해시가 다르면 **제작을 중지**하고 연결 자료부터 찾는다. 관련 없는 파일로 대체하거나 프로토를 봤다고 추정하지 않는다.

## 원고를 화면으로 바꾸기
- 먼저 장면의 학습 목적과 역할을 정한다. 사례는 상황·행동·빠진 절차를 보여주고, 설명은 차이·조건·판단을 풀어낸다. 문장 수대로 같은 카드를 만들지 않는다.
- **대상·행동·관계·조건·판단 중 해당 장면에서 필요한 정보**를 남긴다. 아직 결론을 말하지 않는 도입에는 결론을 지어내지 말고 미제시 이유를 기록한다.
- 정보 이름은 단어로, 비교·원인결과·조건·판단은 의미가 완결되는 짧은 구절/문장으로 쓴다. 명사만 뽑아 문맥을 없애지 않는다.
- 관계에 맞춰 비교·과정·분류·조건·강조를 선택한다. 같은 원/카드를 반복하거나 숫자를 크게 써서 도식화했다고 하지 않는다.
- 아이콘은 개념·행동과 대응시키고 짧은 라벨을 붙인다. 개수나 장식성을 품질 근거로 삼지 않는다.

## 장면별 표현
- **사례:** 프로토 중앙 영상 영역 전체에 관련 상황 영상/이미지와 짧은 자막을 구성한다. 실제 사건과 스톡/생성 재현을 구분한다. 논문·기사 전체 확대를 사례의 기본 배경으로 쓰지 않는다. 필요한 근거 발췌는 보조로 사용한다.
- **강사 설명:** 정보 구조에 맞춰 강사를 좌/우/중앙에 배치한다. 도식이 복잡하면 인물을 생략하고 도식에 영역을 줄 수 있다. 강사 음성이라고 항상 강사 사진을 넣지 않는다.
- **위계:** 소주제·핵심 문장·보조 설명·출처의 역할과 서체를 프로토에서 측정한다. KIRD 심리의 주된 화면 서체는 나눔바른고딕, 일부 말풍선은 나눔고딕이다. 한 크기/서체나 매장 큰 제목 띠를 강제하지 않는다.
- **싱크:** 새 페이지는 #1부터 연속으로 매긴다. 각 번호를 원고 구절과 실제 화면 요소에 연결한다. 원본 #0 등 임시 표시는 복제하지 않는다. 번호 존재를 실제 애니메이션/영상 재생 구현으로 보고하지 않는다.
- **출처:** 자료란에 실제 제공처·ID·웹/PDF 발췌·자체 제작을 구분한다. 상세 URL·권리·원본/삽입 SHA·변환 내용을 연결한다. Getty/MotionElements/Flaticon/AI 표기를 관성적으로 넣지 않는다. 공개 미리보기를 이용허락 취득으로 표시하지 않는다.

## 도구·역할·완료
- PPTX Generator/ppt-master/PptxGenJS/Mermaid/MarkItDown/Playwright/PDF는 보조다. 도구 수·문법·CRC 검사로 교수설계 품질을 판정하지 않는다.
- 기존 PPTX native 구조를 보존한다. PptxGenJS의 기존 PPTX import 지원을 주장하지 않는다. 신규 텍스트·도형·관계는 편집 가능하게 만든다.
- **3 제작 → 2 검수 → 5 별도 사본 디자인 → 3 내용 확인 → 2 재검수 → 1 실제 파일 확인**을 지킨다. 4 자료 지원은 병행할 수 있다.
- 총괄1과 담당2~5의 기존 역할을 재사용한다. 새 이름의 담당을 누적하지 않는다. VS Code 대화 연결과 내부 역할을 구분한다.
- 변경 페이지를 실제 출력과 프로토 옆에 놓고 읽는다. 대상·관계·조건·판단이 이해되는지 구체적인 관측 문장으로 기록한다.
- [네 가지 검수](references/roles-and-review.md)를 모두 통과해야 채택한다. 자동 검사의 human_semantic_review_required를 교육적 품질 PASS로 바꾸지 않는다.
- scripts/prototype_guard.py review --binding <binding.json> --scenes <scene-plan.json> --review <review.json> 으로 같은 PPT/PNG 해시와 역할2/1의 직접 검토 기록을 확인한다.
- 등록/실제 수신/목록 갱신/교육적 품질/사용자 수용을 구분한다. 다른 대화의 자동 로딩이나 모델 설정을 확인 없이 완료로 보고하지 않는다.
