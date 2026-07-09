"""엔드투엔드 테스트: 합성 답안지 생성 → 템플릿 등록 → 채점 → 리포트.

실행: python -m pytest tests/ -v   (또는 python tests/test_omr.py)
"""

import math
import os
import random
import sys
import tempfile

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omr import (
    AnswerKey, Template, build_template_from_image,
    grade_batch, grade_sheet, export_results,
)

NUM_QUESTIONS = 20
NUM_CHOICES = 5
W, H = 900, 1200


def draw_blank_sheet() -> np.ndarray:
    """2단(컬럼당 10문항) x 5지선다 합성 답안지."""
    img = np.full((H, W), 255, np.uint8)
    cv2.rectangle(img, (20, 20), (W - 20, H - 20), 0, 3)  # 테두리 (정렬용)
    cv2.putText(img, "SYNTHETIC OMR SHEET", (60, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    for q in range(NUM_QUESTIONS):
        col = q // 10
        row = q % 10
        base_x = 120 + col * 400
        y = 200 + row * 90
        cv2.putText(img, f"{q + 1}.", (base_x - 60, y + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
        for c in range(NUM_CHOICES):
            cv2.circle(img, (base_x + c * 60, y), 16, 0, 2)
    return img


def bubble_center(q: int, c: int):
    col, row = q // 10, q % 10
    return 120 + (q // 10) * 400 + c * 60, 200 + row * 90


def mark_sheet(blank: np.ndarray, answers: dict) -> np.ndarray:
    """answers: {문항번호(1-base): 선택지 인덱스(0-base) 또는 None(무응답) 또는 리스트(복수)}"""
    img = blank.copy()
    for q, choice in answers.items():
        if choice is None:
            continue
        choices = choice if isinstance(choice, list) else [choice]
        for c in choices:
            x, y = bubble_center(q - 1, c)
            cv2.circle(img, (x, y), 13, 0, -1)
    return img


def distort(img: np.ndarray, angle: float = 2.0, scale: float = 0.95) -> np.ndarray:
    """스캔 왜곡 시뮬레이션: 회전 + 축소 + 노이즈."""
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    out = cv2.warpAffine(img, M, (w, h), borderValue=255)
    noise = np.random.default_rng(42).normal(0, 6, out.shape)
    return np.clip(out.astype(np.float64) + noise, 0, 255).astype(np.uint8)


def test_end_to_end():
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmp:
        # 1) 빈 답안지 → 템플릿
        blank = draw_blank_sheet()
        blank_path = os.path.join(tmp, "blank.png")
        cv2.imwrite(blank_path, blank)
        tpl = build_template_from_image(blank_path, name="test", num_choices=NUM_CHOICES)
        assert len(tpl.questions) == NUM_QUESTIONS, f"문항 수 오탐: {len(tpl.questions)}"
        assert all(len(q.bubbles) == NUM_CHOICES for q in tpl.questions)

        # 저장/로드 왕복
        tpl_path = os.path.join(tmp, "tpl.json")
        tpl.save(tpl_path)
        tpl = Template.load(tpl_path)

        # 2) 정답 가이드 엑셀 생성
        key_answers = {q: random.randrange(NUM_CHOICES) for q in range(1, NUM_QUESTIONS + 1)}
        df = pd.DataFrame({
            "문항": list(key_answers.keys()),
            "정답": [str(c + 1) for c in key_answers.values()],
            "배점": [5] * NUM_QUESTIONS,
        })
        key_path = os.path.join(tmp, "key.xlsx")
        df.to_excel(key_path, index=False)
        key = AnswerKey.load(key_path)
        assert key.total_points == 100

        # 3) 학생 답안 3장 생성 (만점 / 일부 오답+무응답+복수마킹 / 왜곡 스캔)
        scans = os.path.join(tmp, "scans")
        os.makedirs(scans)

        perfect = {q: c for q, c in key_answers.items()}
        cv2.imwrite(os.path.join(scans, "student_perfect.png"),
                    mark_sheet(blank, perfect))

        partial = dict(perfect)
        partial[1] = (key_answers[1] + 1) % NUM_CHOICES   # 오답
        partial[2] = None                                  # 무응답
        partial[3] = [0, 1]                                # 복수 마킹
        cv2.imwrite(os.path.join(scans, "student_partial.png"),
                    mark_sheet(blank, partial))

        cv2.imwrite(os.path.join(scans, "student_distorted.png"),
                    distort(mark_sheet(blank, perfect)))

        # 4) 일괄 채점
        results = grade_batch(scans, tpl, key)
        by_id = {r.sheet_id: r for r in results}

        rp = by_id["student_perfect"]
        assert not rp.error and rp.score == 100, f"만점 답안 채점 실패: {rp.score}"

        rd = by_id["student_distorted"]
        assert not rd.error and rd.score == 100, f"왜곡 스캔 채점 실패: {rd.score}"

        rpart = by_id["student_partial"]
        assert not rpart.error
        assert rpart.score == 85, f"부분 답안 점수 오류: {rpart.score}"
        assert rpart.num_blank == 1 and rpart.num_multiple >= 1

        q3 = next(q for q in rpart.questions if q.number == 3)
        assert q3.status == "multiple" and not q3.is_correct

        # 5) 리포트 export
        out = os.path.join(tmp, "reports")
        created = export_results(results, out, formats=["xlsx", "csv", "json", "html"])
        assert len(created) == 6  # xlsx + csv 3개 + json + html
        for p in created:
            assert os.path.getsize(p) > 0

        summary = pd.read_excel(os.path.join(out, "results.xlsx"), sheet_name="종합")
        assert len(summary) == 3

    print("모든 테스트 통과")


if __name__ == "__main__":
    test_end_to_end()
