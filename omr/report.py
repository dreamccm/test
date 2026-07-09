"""채점 결과 리포트 export.

지원 형식:
    - xlsx: 종합/개별응답/문항분석 3개 시트
    - csv : summary.csv, responses.csv, item_analysis.csv
    - json: 전체 결과 구조화 데이터
    - html: 브라우저/인쇄용 종합 리포트
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime
from typing import List

import pandas as pd

from .grader import SheetResult, item_analysis


def _summary_frame(results: List[SheetResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        if r.error:
            rows.append({"응답자": r.sheet_id, "상태": f"오류: {r.error}"})
            continue
        rows.append({
            "응답자": r.sheet_id,
            "상태": "정상",
            "점수": r.score,
            "만점": r.total_points,
            "득점률(%)": round(r.percentage, 1),
            "정답수": r.num_correct,
            "문항수": r.num_questions,
            "무응답": r.num_blank,
            "복수마킹": r.num_multiple,
        })
    df = pd.DataFrame(rows)
    if "점수" in df.columns:
        df = df.sort_values("점수", ascending=False, na_position="last")
        df.insert(0, "석차", df["점수"].rank(ascending=False, method="min").astype("Int64"))
    return df.reset_index(drop=True)


def _responses_frame(results: List[SheetResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        if r.error:
            continue
        for q in r.questions:
            rows.append({
                "응답자": r.sheet_id,
                "문항": q.number,
                "응답": q.marked or ("무응답" if q.status == "blank" else "복수마킹"),
                "정답": q.correct_answer,
                "정오": "O" if q.is_correct else "X",
                "득점": q.points_earned,
                "배점": q.points_possible,
            })
    return pd.DataFrame(rows)


def _stats(results: List[SheetResult]) -> dict:
    scores = [r.score for r in results if not r.error]
    if not scores:
        return {}
    s = pd.Series(scores)
    return {
        "응시자수": len(scores),
        "평균": round(float(s.mean()), 2),
        "표준편차": round(float(s.std(ddof=0)), 2),
        "최고점": float(s.max()),
        "최저점": float(s.min()),
        "중앙값": float(s.median()),
    }


def export_xlsx(results: List[SheetResult], path: str) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _summary_frame(results).to_excel(writer, sheet_name="종합", index=False)
        _responses_frame(results).to_excel(writer, sheet_name="개별응답", index=False)
        pd.DataFrame(item_analysis(results)).to_excel(writer, sheet_name="문항분석", index=False)
        pd.DataFrame([_stats(results)]).to_excel(writer, sheet_name="통계", index=False)


def export_csv(results: List[SheetResult], out_dir: str) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, df in [
        ("summary", _summary_frame(results)),
        ("responses", _responses_frame(results)),
        ("item_analysis", pd.DataFrame(item_analysis(results))),
    ]:
        p = os.path.join(out_dir, f"{name}.csv")
        df.to_csv(p, index=False, encoding="utf-8-sig")  # 엑셀 한글 호환 BOM
        paths.append(p)
    return paths


def export_json(results: List[SheetResult], path: str) -> None:
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "statistics": _stats(results),
        "item_analysis": item_analysis(results),
        "sheets": [
            {
                "sheet_id": r.sheet_id,
                "image_path": r.image_path,
                "error": r.error,
                "score": r.score if not r.error else None,
                "total_points": r.total_points if not r.error else None,
                "questions": [
                    {
                        "number": q.number,
                        "marked": q.marked,
                        "correct_answer": q.correct_answer,
                        "is_correct": q.is_correct,
                        "points_earned": q.points_earned,
                        "status": q.status,
                    }
                    for q in r.questions
                ],
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _df_to_html_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>데이터 없음</p>"
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
        for row in df.itertuples(index=False)
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def export_html(results: List[SheetResult], path: str, title: str = "OMR 채점 결과") -> None:
    stats = _stats(results)
    stats_html = "".join(
        f"<div class='stat'><div class='label'>{html.escape(str(k))}</div>"
        f"<div class='value'>{html.escape(str(v))}</div></div>"
        for k, v in stats.items()
    )
    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body {{ font-family: 'Malgun Gothic', sans-serif; margin: 2rem; color: #222; }}
 h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
 .stats {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
 .stat {{ border: 1px solid #ddd; border-radius: 8px; padding: .75rem 1.25rem; }}
 .stat .label {{ font-size: .8rem; color: #666; }}
 .stat .value {{ font-size: 1.3rem; font-weight: bold; }}
 table {{ border-collapse: collapse; margin-top: .5rem; }}
 th, td {{ border: 1px solid #ccc; padding: .3rem .7rem; font-size: .85rem; }}
 th {{ background: #f4f4f4; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<h2>통계</h2><div class="stats">{stats_html or '<p>데이터 없음</p>'}</div>
<h2>종합 결과</h2>{_df_to_html_table(_summary_frame(results))}
<h2>문항 분석</h2>{_df_to_html_table(pd.DataFrame(item_analysis(results)))}
<h2>개별 응답</h2>{_df_to_html_table(_responses_frame(results))}
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def export_results(results: List[SheetResult], out_dir: str,
                   formats: List[str] = ("xlsx", "csv", "json", "html")) -> List[str]:
    """요청한 형식들로 일괄 export. 생성된 파일 경로 목록 반환."""
    os.makedirs(out_dir, exist_ok=True)
    created: List[str] = []
    if "xlsx" in formats:
        p = os.path.join(out_dir, "results.xlsx")
        export_xlsx(results, p)
        created.append(p)
    if "csv" in formats:
        created.extend(export_csv(results, out_dir))
    if "json" in formats:
        p = os.path.join(out_dir, "results.json")
        export_json(results, p)
        created.append(p)
    if "html" in formats:
        p = os.path.join(out_dir, "results.html")
        export_html(results, p)
        created.append(p)
    return created
