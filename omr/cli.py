"""명령줄 인터페이스.

사용 예:
    # 1) 빈 답안지에서 템플릿 등록
    python -m omr.cli make-template blank.png --name 중간고사A --choices 5 -o templates/midterm_a.json

    # 2) 채점 (폴더 일괄)
    python -m omr.cli grade scans/ --template templates/midterm_a.json --key answers.xlsx -o results/

    # 3) 템플릿 검증 (버블 감지 결과 오버레이 이미지 생성)
    python -m omr.cli preview templates/midterm_a.json -o preview.png
"""

from __future__ import annotations

import argparse
import sys

from .answer_key import AnswerKey
from .grader import grade_batch, grade_sheet
from .report import export_results
from .template import Template, build_template_from_image


def cmd_make_template(args) -> int:
    labels = args.labels.split(",") if args.labels else None
    tpl = build_template_from_image(
        args.image, name=args.name,
        num_choices=args.choices, choice_labels=labels,
    )
    tpl.save(args.output)
    counts = [len(q.bubbles) for q in tpl.questions]
    print(f"템플릿 저장: {args.output}")
    print(f"  문항 수: {len(tpl.questions)}, 버블 수: {sum(counts)}")
    if counts and len(set(counts)) > 1:
        print("  [주의] 문항별 선택지 수가 일정하지 않습니다. "
              "preview 명령으로 감지 결과를 확인하세요.")
    return 0


def cmd_preview(args) -> int:
    import cv2

    tpl = Template.load(args.template)
    img = cv2.cvtColor(tpl.load_reference(), cv2.COLOR_GRAY2BGR)
    for q in tpl.questions:
        for b in q.bubbles:
            cv2.circle(img, (int(b.x), int(b.y)), int(b.r), (0, 0, 255), 2)
            cv2.putText(img, b.choice, (int(b.x - b.r), int(b.y - b.r - 3)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
        first = q.bubbles[0]
        cv2.putText(img, f"Q{q.number}", (int(first.x - first.r * 3.5), int(first.y + 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 128, 0), 2)
    cv2.imwrite(args.output, img)
    print(f"미리보기 저장: {args.output}")
    return 0


def cmd_grade(args) -> int:
    import os

    tpl = Template.load(args.template)
    key = AnswerKey.load(args.key)

    def progress(done, total, sheet_id):
        print(f"  [{done}/{total}] {sheet_id}")

    if os.path.isdir(args.input):
        print(f"일괄 채점 시작: {args.input}")
        results = grade_batch(args.input, tpl, key,
                              fill_threshold=args.threshold, progress=progress)
    else:
        results = [grade_sheet(args.input, tpl, key, fill_threshold=args.threshold)]

    formats = args.formats.split(",")
    created = export_results(results, args.output, formats=formats)

    ok = [r for r in results if not r.error]
    failed = [r for r in results if r.error]
    print(f"\n채점 완료: 성공 {len(ok)}장 / 실패 {len(failed)}장")
    for r in failed:
        print(f"  실패: {r.sheet_id} — {r.error}")
    if ok:
        avg = sum(r.score for r in ok) / len(ok)
        print(f"평균 점수: {avg:.1f} / {ok[0].total_points:.0f}")
    print("생성된 리포트:")
    for p in created:
        print(f"  {p}")
    return 1 if failed and not ok else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="omr", description="OMR 채점 시스템 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("make-template", help="빈 답안지 이미지에서 템플릿 생성")
    p.add_argument("image", help="빈(미마킹) 답안지 이미지 경로")
    p.add_argument("--name", required=True, help="템플릿 이름")
    p.add_argument("--choices", type=int, default=None, help="문항당 선택지 수 (미지정 시 자동)")
    p.add_argument("--labels", default=None, help="선택지 라벨 (예: A,B,C,D)")
    p.add_argument("-o", "--output", required=True, help="템플릿 JSON 저장 경로")
    p.set_defaults(func=cmd_make_template)

    p = sub.add_parser("preview", help="템플릿 버블 감지 결과 오버레이 이미지 생성")
    p.add_argument("template", help="템플릿 JSON 경로")
    p.add_argument("-o", "--output", default="preview.png")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("grade", help="답안지 이미지(파일 또는 폴더) 채점")
    p.add_argument("input", help="답안지 이미지 파일 또는 폴더")
    p.add_argument("--template", required=True, help="템플릿 JSON 경로")
    p.add_argument("--key", required=True, help="정답 가이드 엑셀(xlsx/csv) 경로")
    p.add_argument("--threshold", type=float, default=0.35, help="마킹 인정 채움 비율 (기본 0.35)")
    p.add_argument("--formats", default="xlsx,csv,json,html",
                   help="리포트 형식 (쉼표 구분: xlsx,csv,json,html)")
    p.add_argument("-o", "--output", default="results", help="리포트 출력 폴더")
    p.set_defaults(func=cmd_grade)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
