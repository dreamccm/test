"""OMR (Optical Mark Recognition) 채점 시스템.

스캔된 답안지 이미지를 템플릿과 비교하여 마킹을 인식하고,
엑셀 정답 가이드 기준으로 채점한 뒤 다양한 형식의 리포트를 생성한다.
"""

__version__ = "1.0.0"

from .template import Template, Question, Bubble, build_template_from_image
from .answer_key import AnswerKey
from .alignment import align_to_template
from .detector import detect_marks
from .grader import grade_sheet, grade_batch, SheetResult
from .report import export_results

__all__ = [
    "Template",
    "Question",
    "Bubble",
    "build_template_from_image",
    "AnswerKey",
    "align_to_template",
    "detect_marks",
    "grade_sheet",
    "grade_batch",
    "SheetResult",
    "export_results",
]
