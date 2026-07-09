"""엑셀 정답 가이드 로드.

지원 형식 (xlsx / xls / csv):
    문항 | 정답 | 배점
    1    | 3    | 4
    2    | 1,4  | 4      ← 복수 정답은 쉼표로 구분
    ...

컬럼명은 유연하게 인식한다:
    문항: 문항, 번호, 문항번호, question, no, q
    정답: 정답, 답, answer, ans, key
    배점: 배점, 점수, points, score (없으면 문항당 1점)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

import pandas as pd

_QUESTION_COLS = {"문항", "번호", "문항번호", "question", "no", "q", "num", "number"}
_ANSWER_COLS = {"정답", "답", "answer", "ans", "key"}
_POINTS_COLS = {"배점", "점수", "points", "score", "point"}


@dataclass
class AnswerKey:
    """문항 번호 → (정답 집합, 배점)."""

    answers: Dict[int, Set[str]] = field(default_factory=dict)
    points: Dict[int, float] = field(default_factory=dict)

    @property
    def total_points(self) -> float:
        return sum(self.points.values())

    @property
    def question_numbers(self) -> List[int]:
        return sorted(self.answers.keys())

    @classmethod
    def load(cls, path: str) -> "AnswerKey":
        if path.lower().endswith(".csv"):
            df = pd.read_csv(path, dtype=str)
        else:
            df = pd.read_excel(path, dtype=str)

        cols = {str(c).strip().lower(): c for c in df.columns}

        def find(names: Set[str]):
            for key, original in cols.items():
                if key in names:
                    return original
            return None

        q_col = find(_QUESTION_COLS)
        a_col = find(_ANSWER_COLS)
        p_col = find(_POINTS_COLS)

        if q_col is None or a_col is None:
            raise ValueError(
                "정답 가이드에서 '문항'과 '정답' 컬럼을 찾을 수 없습니다. "
                f"현재 컬럼: {list(df.columns)}"
            )

        key = cls()
        for _, row in df.iterrows():
            q_raw = row[q_col]
            a_raw = row[a_col]
            if pd.isna(q_raw) or pd.isna(a_raw):
                continue
            number = int(float(str(q_raw).strip()))
            answers = {
                # "3.0" 같은 엑셀 숫자 표기 정규화
                s[:-2] if s.endswith(".0") else s
                for s in (t.strip() for t in str(a_raw).split(","))
                if s
            }
            pts = 1.0
            if p_col is not None and not pd.isna(row[p_col]):
                pts = float(str(row[p_col]).strip())
            key.answers[number] = answers
            key.points[number] = pts

        if not key.answers:
            raise ValueError("정답 가이드에 유효한 문항이 없습니다.")
        return key
