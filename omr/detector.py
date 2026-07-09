"""마킹 인식: 정렬된 스캔 이미지에서 각 버블의 채움 정도를 측정."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import cv2
import numpy as np

from .template import Template


@dataclass
class QuestionMark:
    """문항 하나의 인식 결과."""

    number: int
    selected: List[str]          # 인식된 선택지 (0개=무응답, 2개 이상=복수마킹)
    fill_ratios: Dict[str, float]  # 선택지별 채움 비율 (진단용)

    @property
    def status(self) -> str:
        if len(self.selected) == 0:
            return "blank"        # 무응답
        if len(self.selected) > 1:
            return "multiple"     # 복수 마킹
        return "single"

    @property
    def answer(self) -> str:
        """단일 응답이면 그 값, 아니면 빈 문자열."""
        return self.selected[0] if len(self.selected) == 1 else ""


def _fill_ratio(binary: np.ndarray, x: float, y: float, r: float) -> float:
    """버블 내부의 어두운 픽셀 비율 (0.0~1.0)."""
    h, w = binary.shape
    # 버블 테두리 선 자체는 제외하고 내부만 측정
    rr = max(2.0, r * 0.75)
    x0, x1 = int(max(0, x - rr)), int(min(w, x + rr + 1))
    y0, y1 = int(max(0, y - rr)), int(min(h, y + rr + 1))
    if x0 >= x1 or y0 >= y1:
        return 0.0
    roi = binary[y0:y1, x0:x1]
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = (xx - x) ** 2 + (yy - y) ** 2 <= rr ** 2
    total = int(mask.sum())
    if total == 0:
        return 0.0
    return float((roi > 0)[mask].sum()) / total


def detect_marks(aligned_gray: np.ndarray,
                 template: Template,
                 fill_threshold: float = 0.35,
                 relative_margin: float = 0.25) -> List[QuestionMark]:
    """정렬된 이미지에서 문항별 마킹을 인식한다.

    fill_threshold: 이 비율 이상 채워진 버블만 마킹 후보로 인정.
    relative_margin: 문항 내 최대 채움값 대비 (최대값 - margin) 이상인
                     후보를 모두 선택 처리 → 복수 마킹 검출.
    """
    blur = cv2.GaussianBlur(aligned_gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 51, 12,
    )

    results: List[QuestionMark] = []
    for q in template.questions:
        ratios = {b.choice: _fill_ratio(binary, b.x, b.y, b.r) for b in q.bubbles}
        if not ratios:
            results.append(QuestionMark(q.number, [], {}))
            continue

        max_fill = max(ratios.values())
        if max_fill < fill_threshold:
            selected: List[str] = []
        else:
            selected = [c for c, v in ratios.items()
                        if v >= fill_threshold and v >= max_fill - relative_margin]

        results.append(QuestionMark(
            number=q.number,
            selected=selected,
            fill_ratios={c: round(v, 3) for c, v in ratios.items()},
        ))
    return results
