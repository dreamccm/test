"""Windows용 GUI (Tkinter — Python 기본 포함, 별도 설치 불필요).

실행:  python -m omr.gui

워크플로:
    1. [템플릿] 탭: 빈 답안지 이미지 선택 → 버블 자동 감지 → 템플릿 저장
    2. [채점] 탭: 템플릿 + 정답 엑셀 + 스캔 폴더 선택 → 채점 실행
    3. 결과를 원하는 형식(xlsx/csv/json/html)으로 export
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .answer_key import AnswerKey
from .grader import grade_batch
from .report import export_results
from .template import Template, build_template_from_image


class OmrApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OMR 채점 시스템")
        self.geometry("860x640")
        self.results = []

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_template_tab(notebook)
        self._build_grade_tab(notebook)

    # ---------- 공통 위젯 ----------

    def _file_row(self, parent, label, var, row, filetypes=None, is_dir=False, save=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(parent, textvariable=var, width=64).grid(row=row, column=1, padx=4, pady=4)

        def browse():
            if is_dir:
                path = filedialog.askdirectory()
            elif save:
                path = filedialog.asksaveasfilename(filetypes=filetypes or [],
                                                    defaultextension=filetypes[0][1].lstrip("*") if filetypes else "")
            else:
                path = filedialog.askopenfilename(filetypes=filetypes or [])
            if path:
                var.set(path)

        ttk.Button(parent, text="찾아보기...", command=browse).grid(row=row, column=2, padx=4)

    # ---------- 템플릿 탭 ----------

    def _build_template_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="1. 템플릿 등록")

        self.tpl_image = tk.StringVar()
        self.tpl_name = tk.StringVar(value="새 템플릿")
        self.tpl_choices = tk.StringVar()
        self.tpl_output = tk.StringVar()

        img_types = [("이미지", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")]
        self._file_row(tab, "빈 답안지 이미지", self.tpl_image, 0, img_types)
        ttk.Label(tab, text="템플릿 이름").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(tab, textvariable=self.tpl_name, width=32).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(tab, text="선택지 수 (비우면 자동)").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(tab, textvariable=self.tpl_choices, width=8).grid(row=2, column=1, sticky="w", padx=4)
        self._file_row(tab, "템플릿 저장 경로", self.tpl_output, 3,
                       [("템플릿 JSON", "*.json")], save=True)

        ttk.Button(tab, text="버블 감지 및 템플릿 저장",
                   command=self._make_template).grid(row=4, column=1, sticky="w", padx=4, pady=12)

        self.tpl_log = tk.Text(tab, height=18, state="disabled")
        self.tpl_log.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)
        tab.rowconfigure(5, weight=1)
        tab.columnconfigure(1, weight=1)

    def _make_template(self):
        image, out = self.tpl_image.get(), self.tpl_output.get()
        if not image or not out:
            messagebox.showwarning("입력 필요", "이미지와 저장 경로를 지정하세요.")
            return
        try:
            choices = int(self.tpl_choices.get()) if self.tpl_choices.get().strip() else None
            tpl = build_template_from_image(image, name=self.tpl_name.get(), num_choices=choices)
            tpl.save(out)
            counts = [len(q.bubbles) for q in tpl.questions]
            msg = (f"템플릿 저장 완료: {out}\n"
                   f"감지된 문항 수: {len(tpl.questions)}, 총 버블 수: {sum(counts)}\n")
            if counts and len(set(counts)) > 1:
                msg += "[주의] 문항별 선택지 수가 일정하지 않습니다. 감지 결과를 확인하세요.\n"
            self._log(self.tpl_log, msg)
        except Exception as exc:
            messagebox.showerror("오류", str(exc))

    # ---------- 채점 탭 ----------

    def _build_grade_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="2. 채점 및 리포트")

        self.gr_template = tk.StringVar()
        self.gr_key = tk.StringVar()
        self.gr_scans = tk.StringVar()
        self.gr_output = tk.StringVar(value=os.path.abspath("results"))

        self._file_row(tab, "템플릿 JSON", self.gr_template, 0, [("템플릿 JSON", "*.json")])
        self._file_row(tab, "정답 가이드 (엑셀/CSV)", self.gr_key, 1,
                       [("엑셀/CSV", "*.xlsx *.xls *.csv")])
        self._file_row(tab, "답안지 스캔 폴더", self.gr_scans, 2, is_dir=True)
        self._file_row(tab, "리포트 출력 폴더", self.gr_output, 3, is_dir=True)

        fmt_frame = ttk.Frame(tab)
        fmt_frame.grid(row=4, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(fmt_frame, text="리포트 형식: ").pack(side="left")
        self.fmt_vars = {}
        for fmt in ("xlsx", "csv", "json", "html"):
            v = tk.BooleanVar(value=fmt in ("xlsx", "html"))
            self.fmt_vars[fmt] = v
            ttk.Checkbutton(fmt_frame, text=fmt.upper(), variable=v).pack(side="left", padx=4)

        self.grade_btn = ttk.Button(tab, text="채점 실행", command=self._start_grading)
        self.grade_btn.grid(row=5, column=1, sticky="w", padx=4, pady=8)

        self.progress = ttk.Progressbar(tab, mode="determinate")
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", padx=4)

        self.gr_log = tk.Text(tab, height=16, state="disabled")
        self.gr_log.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)
        tab.rowconfigure(7, weight=1)
        tab.columnconfigure(1, weight=1)

    def _start_grading(self):
        tpl_path, key_path, scans = self.gr_template.get(), self.gr_key.get(), self.gr_scans.get()
        if not (tpl_path and key_path and scans):
            messagebox.showwarning("입력 필요", "템플릿, 정답 가이드, 스캔 폴더를 모두 지정하세요.")
            return
        formats = [f for f, v in self.fmt_vars.items() if v.get()]
        if not formats:
            messagebox.showwarning("입력 필요", "리포트 형식을 하나 이상 선택하세요.")
            return

        self.grade_btn.config(state="disabled")
        threading.Thread(target=self._run_grading,
                         args=(tpl_path, key_path, scans, self.gr_output.get(), formats),
                         daemon=True).start()

    def _run_grading(self, tpl_path, key_path, scans, out_dir, formats):
        try:
            tpl = Template.load(tpl_path)
            key = AnswerKey.load(key_path)

            def progress(done, total, sheet_id):
                self.after(0, lambda: self._update_progress(done, total, sheet_id))

            results = grade_batch(scans, tpl, key, progress=progress)
            created = export_results(results, out_dir, formats=formats)

            ok = [r for r in results if not r.error]
            failed = [r for r in results if r.error]
            lines = [f"\n채점 완료: 성공 {len(ok)}장 / 실패 {len(failed)}장"]
            for r in failed:
                lines.append(f"  실패: {r.sheet_id} — {r.error}")
            if ok:
                avg = sum(r.score for r in ok) / len(ok)
                lines.append(f"평균 점수: {avg:.1f} / {ok[0].total_points:.0f}")
            lines.append("생성된 리포트:")
            lines.extend(f"  {p}" for p in created)
            self.after(0, lambda: self._log(self.gr_log, "\n".join(lines) + "\n"))
        except Exception as exc:
            self.after(0, lambda exc=exc: messagebox.showerror("오류", str(exc)))
        finally:
            self.after(0, lambda: self.grade_btn.config(state="normal"))

    def _update_progress(self, done, total, sheet_id):
        self.progress["maximum"] = total
        self.progress["value"] = done
        self._log(self.gr_log, f"[{done}/{total}] {sheet_id}\n")

    # ---------- 로그 ----------

    @staticmethod
    def _log(widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.insert("end", text)
        widget.see("end")
        widget.config(state="disabled")


def main():
    OmrApp().mainloop()


if __name__ == "__main__":
    main()
