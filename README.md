# OMR 채점 시스템

스캔된 답안지 이미지를 불러와 마킹을 인식하고, 엑셀 정답 가이드 기준으로
자동 채점한 뒤 다양한 형식의 리포트를 생성하는 시스템입니다.

- **사용 환경**: Windows 10/11 (Python 3.10 이상)
- **입력**: 기존 스캔 이미지 (PNG / JPG / BMP / TIFF)
- **정답 가이드**: 엑셀(xlsx/xls) 또는 CSV 업로드
- **템플릿**: 다양한 사이즈·디자인의 답안지를 각각 템플릿으로 등록 후 재사용
- **리포트**: Excel / CSV / JSON / HTML export

## 설치 (Windows)

```bat
:: Python 3.10+ 설치 후 (python.org, "Add to PATH" 체크)
pip install -r requirements.txt
```

## 사용 방법

### GUI (권장)

```bat
python -m omr.gui
```

1. **템플릿 등록 탭**: 빈(미마킹) 답안지 스캔 이미지를 선택하면 마킹 버블을
   자동 감지하여 템플릿(JSON)으로 저장합니다. 답안지 디자인/사이즈별로
   템플릿을 하나씩 등록해 두고 재사용합니다.
2. **채점 탭**: 템플릿 + 정답 엑셀 + 스캔 이미지 폴더를 지정하고 채점을
   실행합니다. 완료 후 선택한 형식으로 리포트가 생성됩니다.

### CLI

```bat
:: 1) 빈 답안지에서 템플릿 생성
python -m omr.cli make-template blank.png --name 중간고사A --choices 5 -o templates\midterm_a.json

:: 2) 감지 결과 확인 (버블 위치·문항 번호 오버레이 이미지)
python -m omr.cli preview templates\midterm_a.json -o preview.png

:: 3) 스캔 폴더 일괄 채점 + 리포트 생성
python -m omr.cli grade scans\ --template templates\midterm_a.json --key answers.xlsx -o results\
```

## 정답 가이드 엑셀 형식

| 문항 | 정답 | 배점 |
|------|------|------|
| 1    | 3    | 4    |
| 2    | 1,4  | 4    |
| 3    | 2    | 5    |

- 복수 정답은 쉼표로 구분합니다 (모두 마킹해야 정답 처리).
- 컬럼명은 `문항/번호/question/no`, `정답/답/answer`, `배점/점수/points` 등을 인식합니다.
- 배점 컬럼이 없으면 문항당 1점으로 처리합니다.
- 예시 파일: [`examples/answer_key_sample.csv`](examples/answer_key_sample.csv)

## 동작 원리

1. **템플릿 등록** (`omr/template.py`): 빈 답안지에서 원형 윤곽을 감지하고
   반지름·격자 일관성 필터로 오탐(문항 번호 숫자, 로고 등)을 제거한 뒤,
   행(문항) × 열(선택지) 격자로 묶어 JSON으로 저장합니다. 다단(멀티 컬럼)
   레이아웃을 자동 인식하며, 문항 번호는 "왼쪽 단부터 위→아래" 순서로 배정됩니다.
2. **이미지 정렬** (`omr/alignment.py`): 제출 답안 스캔본을 ORB 특징점 매칭 +
   호모그래피로 템플릿 좌표계에 정렬합니다 (회전·이동·크기·기울어짐 보정).
   실패 시 답안지 외곽 사각형 검출로 폴백합니다.
3. **마킹 인식** (`omr/detector.py`): 각 버블 내부의 채움 비율을 측정하여
   응답을 판정합니다. 무응답·복수 마킹을 구분해 기록합니다.
4. **채점** (`omr/grader.py`): 정답 가이드와 대조하여 문항별 득점을 계산합니다.
   한 장의 처리 실패가 일괄 채점 전체를 중단시키지 않습니다.
5. **리포트** (`omr/report.py`):
   - `results.xlsx` — 종합(석차 포함) / 개별응답 / 문항분석 / 통계 시트
   - `summary.csv`, `responses.csv`, `item_analysis.csv`
   - `results.json` — 구조화 데이터 (외부 시스템 연동용)
   - `results.html` — 브라우저 열람·인쇄용 리포트

## 채점 파라미터

- `--threshold` (기본 0.35): 버블이 이 비율 이상 채워져야 마킹으로 인정.
  연필 마킹이 흐려 무응답이 많이 나오면 낮추고(예: 0.25),
  인쇄가 진해 오탐이 나오면 높입니다(예: 0.45).

## 테스트

```bat
python tests\test_omr.py
```

합성 답안지 생성 → 템플릿 등록 → 마킹(정답/오답/무응답/복수마킹) →
회전·노이즈 왜곡 스캔 → 채점 → 4종 리포트 export까지 검증합니다.

## 프로젝트 구조

```
omr/
  template.py    # 템플릿 정의·자동 감지·JSON 저장/로드
  alignment.py   # 스캔 이미지 → 템플릿 좌표계 정렬
  detector.py    # 버블 채움 비율 측정, 마킹 판정
  answer_key.py  # 엑셀/CSV 정답 가이드 로드
  grader.py      # 채점, 일괄 처리, 문항 분석
  report.py      # Excel/CSV/JSON/HTML 리포트 export
  cli.py         # 명령줄 인터페이스
  gui.py         # Windows GUI (Tkinter)
tests/
  test_omr.py    # 엔드투엔드 테스트
examples/
  answer_key_sample.csv
```
