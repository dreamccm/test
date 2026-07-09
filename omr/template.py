"""답안지 템플릿 정의 및 자동 인식.

템플릿은 빈(미마킹) 답안지 이미지 한 장으로부터 생성한다.
버블(마킹 원)을 자동 감지하여 행(문항) x 열(선택지) 격자로 묶고,
JSON 파일로 저장/로드한다. 서로 다른 사이즈·디자인의 답안지는
각각 별도 템플릿으로 등록하면 된다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import cv2
import numpy as np


@dataclass
class Bubble:
    """마킹 버블 하나의 위치 (템플릿 기준 좌표, 픽셀)."""

    x: float          # 중심 x
    y: float          # 중심 y
    r: float          # 반지름
    choice: str       # 선택지 라벨 (예: "1", "2", "A", "B")


@dataclass
class Question:
    """문항 하나: 선택지 버블 목록."""

    number: int
    bubbles: List[Bubble] = field(default_factory=list)


@dataclass
class Template:
    """답안지 템플릿.

    reference_image: 정렬 기준이 되는 빈 답안지 이미지 경로.
    width/height: 기준 이미지 크기. 스캔본은 이 크기로 정렬된다.
    """

    name: str
    reference_image: str
    width: int
    height: int
    questions: List[Question] = field(default_factory=list)
    choice_labels: List[str] = field(default_factory=lambda: ["1", "2", "3", "4", "5"])

    # ---- 직렬화 ----

    def save(self, path: str) -> None:
        data = asdict(self)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Template":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        questions = [
            Question(
                number=q["number"],
                bubbles=[Bubble(**b) for b in q["bubbles"]],
            )
            for q in data["questions"]
        ]
        return cls(
            name=data["name"],
            reference_image=data["reference_image"],
            width=data["width"],
            height=data["height"],
            questions=questions,
            choice_labels=data.get("choice_labels", ["1", "2", "3", "4", "5"]),
        )

    def load_reference(self) -> np.ndarray:
        """기준 이미지를 그레이스케일로 로드."""
        img = cv2.imread(self.reference_image, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"템플릿 기준 이미지를 열 수 없습니다: {self.reference_image}")
        return img


# ---------------------------------------------------------------------------
# 템플릿 자동 생성: 빈 답안지에서 버블 감지
# ---------------------------------------------------------------------------

def _detect_bubbles(gray: np.ndarray,
                    min_radius: int = 6,
                    max_radius: int = 40) -> List[tuple]:
    """빈 답안지에서 버블(원형 윤곽) 후보를 감지해 (x, y, r) 목록 반환."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 10,
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < np.pi * min_radius ** 2 * 0.5:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        if not (min_radius <= r <= max_radius):
            continue
        # 원형도 검사: 윤곽 면적 vs 외접원 면적
        circularity = area / (np.pi * r * r)
        if circularity < 0.55:
            continue
        peri = cv2.arcLength(c, True)
        if peri == 0:
            continue
        roundness = 4 * np.pi * area / (peri * peri)
        if roundness < 0.6:
            continue
        candidates.append((float(x), float(y), float(r)))

    # 중복(동심) 후보 제거
    candidates.sort(key=lambda t: -t[2])
    kept: List[tuple] = []
    for x, y, r in candidates:
        if all((x - kx) ** 2 + (y - ky) ** 2 > (0.8 * (r + kr)) ** 2 for kx, ky, kr in kept):
            kept.append((x, y, r))
    return kept


def _cluster_1d(values: List[float], tol: float) -> List[List[int]]:
    """1차원 값들을 tol 이내로 묶어 인덱스 클러스터 목록 반환 (값 오름차순)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    clusters: List[List[int]] = []
    for i in order:
        if clusters and values[i] - values[clusters[-1][-1]] <= tol:
            clusters[-1].append(i)
        else:
            clusters.append([i])
    return clusters


def build_template_from_image(image_path: str,
                              name: str,
                              num_choices: Optional[int] = None,
                              choice_labels: Optional[List[str]] = None,
                              question_start: int = 1) -> Template:
    """빈 답안지 이미지에서 템플릿을 자동 생성한다.

    버블을 감지한 뒤 y좌표로 행(문항), 행 내 x좌표 순서로 선택지를 배정한다.
    다단(멀티 컬럼) 답안지는 행 클러스터 내에서 x 간격이 크게 벌어지는 지점을
    기준으로 문항 그룹을 분리한다.

    num_choices: 문항당 선택지 수. 지정하면 해당 개수 단위로 그룹을 나누고,
                 미지정 시 x 간격 기반으로 자동 추정한다.
    """
    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {image_path}")
    h, w = gray.shape

    bubbles = _detect_bubbles(gray)
    if not bubbles:
        raise ValueError("버블을 감지하지 못했습니다. 이미지 해상도/품질을 확인하세요.")

    median_r = float(np.median([b[2] for b in bubbles]))

    # 반지름 일관성 필터: 문항 번호 숫자(0,6,8,9 등)의 둥근 획 오탐 제거
    bubbles = [b for b in bubbles if 0.7 * median_r <= b[2] <= 1.4 * median_r]

    # 격자 일관성 필터: 실제 버블은 페이지 전체에서 같은 x 컬럼에 반복 등장한다.
    # 소수의 버블만 있는 x 위치(인쇄된 글자·로고 등의 오탐)는 제거.
    xs = [b[0] for b in bubbles]
    x_clusters = _cluster_1d(xs, tol=median_r)
    max_support = max(len(c) for c in x_clusters)
    if max_support >= 6:
        min_support = max(3, int(np.ceil(0.5 * max_support)))
        keep = sorted(i for c in x_clusters if len(c) >= min_support for i in c)
        if keep:
            bubbles = [bubbles[i] for i in keep]

    # 행 클러스터링 (y 기준)
    ys = [b[1] for b in bubbles]
    row_clusters = _cluster_1d(ys, tol=median_r * 1.2)

    # 각 행에서 x 순으로 정렬 후 문항 그룹 분리
    groups: List[List[tuple]] = []  # 각 그룹 = 문항 하나의 버블들
    for row in row_clusters:
        row_bubbles = sorted((bubbles[i] for i in row), key=lambda b: b[0])
        if num_choices:
            for i in range(0, len(row_bubbles), num_choices):
                chunk = row_bubbles[i:i + num_choices]
                if len(chunk) == num_choices:
                    groups.append(chunk)
        else:
            # 인접 버블 간 x 간격의 급증 지점에서 분리
            if len(row_bubbles) == 1:
                groups.append(row_bubbles)
                continue
            gaps = [row_bubbles[i + 1][0] - row_bubbles[i][0]
                    for i in range(len(row_bubbles) - 1)]
            typical = float(np.median(gaps))
            current = [row_bubbles[0]]
            for i, g in enumerate(gaps):
                if g > typical * 2.0:
                    groups.append(current)
                    current = []
                current.append(row_bubbles[i + 1])
            groups.append(current)

    # 문항 번호 배정: 컬럼(그룹의 시작 x) 우선, 그 다음 y 순서
    # → 일반적인 다단 답안지의 "위에서 아래, 왼쪽 단부터" 순서를 따른다.
    group_x = [min(b[0] for b in g) for g in groups]
    col_clusters = _cluster_1d(group_x, tol=median_r * 4)

    questions: List[Question] = []
    number = question_start
    for col in col_clusters:
        col_groups = sorted((groups[i] for i in col), key=lambda g: g[0][1])
        for g in col_groups:
            n = len(g)
            labels = choice_labels or [str(i + 1) for i in range(n)]
            q = Question(
                number=number,
                bubbles=[Bubble(x=b[0], y=b[1], r=b[2], choice=labels[i])
                         for i, b in enumerate(g)],
            )
            questions.append(q)
            number += 1

    counts = [len(q.bubbles) for q in questions]
    common = int(np.bincount(counts).argmax()) if counts else 0
    final_labels = choice_labels or [str(i + 1) for i in range(common)]

    return Template(
        name=name,
        reference_image=os.path.abspath(image_path),
        width=w,
        height=h,
        questions=questions,
        choice_labels=final_labels,
    )
