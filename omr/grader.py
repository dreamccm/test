"""채점: 마킹 인식 결과 + 정답 가이드 → 채점 결과."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .alignment import align_to_template
from .answer_key import AnswerKey
from .detector import QuestionMark, detect_marks
from .template import Template


@dataclass
class QuestionResult:
    """문항 하나의 채점 결과."""

    number: int
    marked: str            # 인식된 응답 ("" = 무응답/복수마킹)
    correct_answer: str    # 정답 (복수면 "1,3" 형태)
    is_correct: bool
    points_earned: float
    points_possible: float
    status: str            # single / blank / multiple


@dataclass
class SheetResult:
    """응답자 한 명(답안지 한 장)의 채점 결과."""

    sheet_id: str                      # 파일명 기반 식별자
    image_path: str
    questions: List[QuestionResult] = field(default_factory=list)
    error: Optional[str] = None        # 처리 실패 시 사유

    @property
    def score(self) -> float:
        return sum(q.points_earned for q in self.questions)

    @property
    def total_points(self) -> float:
        return sum(q.points_possible for q in self.questions)

    @property
    def num_correct(self) -> int:
        return sum(1 for q in self.questions if q.is_correct)

    @property
    def num_questions(self) -> int:
        return len(self.questions)

    @property
    def num_blank(self) -> int:
        return sum(1 for q in self.questions if q.status == "blank")

    @property
    def num_multiple(self) -> int:
        return sum(1 for q in self.questions if q.status == "multiple")

    @property
    def percentage(self) -> float:
        return self.score / self.total_points * 100 if self.total_points else 0.0


def _grade_marks(marks: List[QuestionMark], key: AnswerKey) -> List[QuestionResult]:
    by_number = {m.number: m for m in marks}
    results: List[QuestionResult] = []
    for number in key.question_numbers:
        correct_set = key.answers[number]
        pts = key.points[number]
        mark = by_number.get(number)

        if mark is None:
            results.append(QuestionResult(
                number=number, marked="", correct_answer=",".join(sorted(correct_set)),
                is_correct=False, points_earned=0.0, points_possible=pts,
                status="blank",
            ))
            continue

        # 복수 정답 문항: 마킹 집합이 정답 집합과 일치해야 정답 처리
        marked_set = set(mark.selected)
        is_correct = bool(marked_set) and marked_set == correct_set
        results.append(QuestionResult(
            number=number,
            marked=",".join(mark.selected),
            correct_answer=",".join(sorted(correct_set)),
            is_correct=is_correct,
            points_earned=pts if is_correct else 0.0,
            points_possible=pts,
            status=mark.status,
        ))
    return results


def grade_sheet(image_path: str,
                template: Template,
                key: AnswerKey,
                fill_threshold: float = 0.35) -> SheetResult:
    """답안지 이미지 한 장을 채점한다."""
    sheet_id = os.path.splitext(os.path.basename(image_path))[0]
    try:
        aligned = align_to_template(image_path, template)
        marks = detect_marks(aligned, template, fill_threshold=fill_threshold)
        return SheetResult(
            sheet_id=sheet_id,
            image_path=image_path,
            questions=_grade_marks(marks, key),
        )
    except Exception as exc:  # 배치 처리에서 한 장 실패가 전체를 막지 않도록
        return SheetResult(sheet_id=sheet_id, image_path=image_path, error=str(exc))


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def grade_batch(image_dir: str,
                template: Template,
                key: AnswerKey,
                fill_threshold: float = 0.35,
                progress=None) -> List[SheetResult]:
    """폴더 내 모든 답안지 이미지를 일괄 채점한다.

    progress: 콜백 (done, total, sheet_id) — GUI/CLI 진행 표시용.
    """
    files = sorted(
        os.path.join(image_dir, f) for f in os.listdir(image_dir)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
    )
    if not files:
        raise ValueError(f"폴더에 이미지 파일이 없습니다: {image_dir}")

    results: List[SheetResult] = []
    for i, path in enumerate(files, 1):
        result = grade_sheet(path, template, key, fill_threshold=fill_threshold)
        results.append(result)
        if progress:
            progress(i, len(files), result.sheet_id)
    return results


def item_analysis(results: List[SheetResult]) -> List[Dict]:
    """문항별 정답률/무응답률/복수마킹률 분석."""
    graded = [r for r in results if not r.error]
    if not graded:
        return []
    rows: List[Dict] = []
    numbers = [q.number for q in graded[0].questions]
    for number in numbers:
        qs = [q for r in graded for q in r.questions if q.number == number]
        n = len(qs)
        rows.append({
            "문항": number,
            "정답": qs[0].correct_answer if qs else "",
            "배점": qs[0].points_possible if qs else 0,
            "응시자수": n,
            "정답자수": sum(1 for q in qs if q.is_correct),
            "정답률(%)": round(sum(1 for q in qs if q.is_correct) / n * 100, 1) if n else 0,
            "무응답수": sum(1 for q in qs if q.status == "blank"),
            "복수마킹수": sum(1 for q in qs if q.status == "multiple"),
        })
    return rows
