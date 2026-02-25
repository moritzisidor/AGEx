#!/usr/bin/env python3
"""generate_answer_sheets.py
-------------------------
Generates:
- One combined PDF with all answer sheets (answer_sheets_all.pdf)
- One combined PDF with all cover sheets (cover_sheets_all.pdf) if --cover-tex is used
- One solution PDF (answer_sheet_solution.pdf)

It can also (optionally) keep per-student PDFs for debugging/printing.

What it does
- Renders answer sheets with ReportLab.
- Optionally renders cover sheets by compiling a LaTeX wrapper that \\input{}'s a
  user-maintained .tex content file.
- Merges the per-student PDFs into combined PDFs.

Requirements (for cover sheets)
- A working LaTeX installation that provides 'pdflatex' (e.g., MacTeX).
- Python package 'pypdf' (preferred) or 'PyPDF2' for merging (optional).
  If not installed, you can still generate separate PDFs.

For usage check 


"""
from __future__ import annotations

import argparse, json, os, string, math, shutil, tempfile, subprocess
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import date
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.lib import colors

PAPERS = {"A4": A4, "LETTER": letter}

# ----------------------------
# Original helper functions (unchanged)
# ----------------------------
def parse_csv(s: str):
    return [x.strip() for x in s.split(",") if x.strip()]

def option_labels(n: int):
    letters = list(string.ascii_uppercase)
    if n <= 26:
        return letters[:n]
    out = letters[:]
    i = 0
    while len(out) < n:
        out.append(letters[i // 26] + letters[i % 26])
        i += 1
    return out[:n]

def parse_per_question_counts(spec: str, num_questions: int):
    raw = parse_csv(spec)
    counts = [int(x) for x in raw]
    return [counts[i % len(counts)] for i in range(num_questions)]

def parse_answer_key(spec: str, num_questions: int):
    raw = parse_csv(spec)
    return [raw[i % len(raw)] for i in range(num_questions)]

def draw_corner_markers(c, W, H, margin, marker_size):
    c.setFillColor(colors.black)
    for (x, y) in [
        (margin, margin),
        (W - margin - marker_size, margin),
        (margin, H - margin - marker_size),
        (W - margin - marker_size, H - margin - marker_size),
    ]:
        c.rect(x, y, marker_size, marker_size, fill=1, stroke=0)

@dataclass
class Box:
    q: int
    opt: int
    x_pt: float
    y_pt: float
    w_pt: float
    h_pt: float

def compute_layout(paper, title, num_questions, per_q_counts,
                   columns, force_columns,
                   row_gap_mm, col_gap_mm, box_size_mm):
    W, H = PAPERS[paper]

    margin = 12 * mm
    marker_size = 9 * mm

    box_size = box_size_mm * mm
    box_gap_y = 4.0 * mm
    opt_label_gap = 2.5 * mm

    base_question_gap_y = 6.0 * mm
    base_col_gap_x = 10.0 * mm

    question_gap_y = base_question_gap_y + row_gap_mm * mm
    col_gap_x = base_col_gap_x + col_gap_mm * mm

    top_title_gap = 14 * mm

    max_k = max(per_q_counts)

    usable_top = H - margin
    usable_bottom = margin
    usable_left = margin
    usable_right = W - margin

    # Reserve space for markers + header + title + student ID
    top_reserved = (
        marker_size + 6*mm + 10*mm + 6*mm + 10*mm + 4*mm + 2*mm
    )
    content_top = (H - margin) - top_reserved
    available_h = content_top - usable_bottom

    q_block_h = max_k * box_size + (max_k - 1) * box_gap_y + question_gap_y
    rows_fit = int(available_h // q_block_h)
    if rows_fit <= 0:
        raise SystemExit("Layout too tight.")

    if force_columns:
        cols_used = columns
        rows = int(math.ceil(num_questions / cols_used))
    else:
        cols_used = min(columns, int(math.ceil(num_questions / rows_fit)))
        rows = int(math.ceil(num_questions / cols_used))

    col_width = (usable_right - usable_left - (cols_used - 1) * col_gap_x) / cols_used

    boxes = []
    for r in range(rows):
        y_row_top = content_top - r * q_block_h
        for cidx in range(cols_used):
            q = r * cols_used + cidx + 1
            if q > num_questions:
                break
            k = per_q_counts[q - 1]
            box_y_top = y_row_top - 8 * mm
            col_x = usable_left + cidx * (col_width + col_gap_x)
            for oi in range(k):
                yy = box_y_top - oi * (box_size + box_gap_y)
                boxes.append(Box(q, oi, float(col_x), float(yy), float(box_size), float(box_size)))

    return {
        "paper": paper,
        "title": title,
        "page_width_pt": float(W),
        "page_height_pt": float(H),
        "canonical_w_px": 2480,
        "canonical_h_px": 3508,
        "num_questions": num_questions,
        "per_question_option_counts": per_q_counts,
        "options_list": per_q_counts,
        "marker": {"margin_pt": float(margin), "size_pt": float(marker_size)},
        "geometry": {
            "box_size_pt": float(box_size),
            "box_gap_y_pt": float(box_gap_y),
            "opt_label_gap_pt": float(opt_label_gap),
        },
        "boxes": [b.__dict__ for b in boxes],
        "student_id_print": {"x_pt": float(usable_left), "y_pt": float(usable_top - top_title_gap - 2 * mm)},
        "answer_key": [],
    }

def render_sheet(path, layout, student_id, fill_solution,
                 course_name="", professor="", exam_date=""):

    W, H = PAPERS[layout["paper"]]
    c = canvas.Canvas(path, pagesize=(W, H))

    # Auto date if not provided
    if not exam_date:
        exam_date = date.today().strftime("%d. %B %Y")

    margin = layout["marker"]["margin_pt"]
    marker_size = layout["marker"]["size_pt"]

    # Corner markers
    draw_corner_markers(c, W, H, margin, marker_size)

    # ---- HEADER BAND (below markers) ----
    header_y = (H - margin) - marker_size - 6*mm

    c.setFont("Times-Bold", 14)
    if course_name:
        c.drawString(margin, header_y, course_name)

    c.setFont("Times-Roman", 12)
    if professor:
        c.drawRightString(W - margin, header_y, professor)
    c.drawRightString(W - margin, header_y - 12, exam_date)

    rule_y = header_y - 18
    c.setLineWidth(1)
    c.line(margin, rule_y, W - margin, rule_y)

    # ---- TITLE BAND ----
    title_y = rule_y - 28
    c.setFont("Times-Bold", 26)
    c.drawCentredString(W / 2, title_y, layout["title"])

    # Student ID under title (left)
    if student_id:
        c.setFont("Times-Bold", 14)
        c.drawString(margin, title_y - 18, f"Student ID: {student_id}")

    # ---- QUESTIONS / BOXES ----
    boxes_by_q: Dict[int, List[Dict[str, Any]]] = {}
    for b in layout["boxes"]:
        boxes_by_q.setdefault(int(b["q"]), []).append(b)
    for q in boxes_by_q:
        boxes_by_q[q].sort(key=lambda x: x["opt"])

    for q in sorted(boxes_by_q.keys()):
        bxs = boxes_by_q[q]
        first = bxs[0]

        c.setFont("Times-Bold", 14)
        prefix = layout.get("question_prefix", "")
        if prefix:
            prefix_str = str(prefix).rstrip(".")
            qlabel = f"{prefix_str}.{q}"
        else:
            qlabel = str(q)
        c.drawString(first["x_pt"], first["y_pt"] + first["h_pt"] + 2.5 * mm, f"Q {qlabel}")

        c.setFont("Times-Roman", 12)
        labels = option_labels(layout["per_question_option_counts"][q - 1])

        for b in bxs:
            c.rect(b["x_pt"], b["y_pt"], b["w_pt"], b["h_pt"])

            if fill_solution and layout["answer_key"][q - 1] == b["opt"]:
                c.rect(
                    b["x_pt"],
                    b["y_pt"],
                    b["w_pt"],
                    b["h_pt"],
                    fill=1,
                    stroke=0
                )

            c.drawString(
                b["x_pt"] + b["w_pt"] + layout["geometry"]["opt_label_gap_pt"],
                b["y_pt"] + 0.5 * mm,
                f"({labels[b['opt']]})"
            )

    c.showPage()
    c.save()

# ----------------------------
# New: LaTeX cover sheet pipeline
# ----------------------------
_LATEX_WRAPPER = r"""
\documentclass[a4paper,11pt]{article}

\usepackage[ngerman]{babel}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{setspace}
\usepackage[margin=18mm]{geometry}

\pagestyle{empty}

\newcommand{\CourseName}{%(course)s}
\newcommand{\Professor}{%(prof)s}
\newcommand{\ExamDate}{%(date)s}
\newcommand{\StudentID}{%(sid)s}
\newcommand{\CoverTitle}{%(cover_title)s}

\begin{document}

\begin{center}
{\Large \textbf{\CourseName}}\\
\vspace{0.2cm}
{\ \Professor \hfill \ExamDate}
\end{center}

\vspace{0.5cm}

\noindent
\Large \textbf{\CoverTitle} \hfill \Large \textbf{Student-ID:} \Large \StudentID
\normalsize

\vspace{0.8cm}

%% Embedded content (user-maintained)
\input{cover_content.tex}

\end{document}
"""

def _latex_escape(s: str) -> str:
    """Escape strings for safe insertion into LaTeX macro definitions."""
    if s is None:
        return ""
    # Minimal escaping for common special chars.
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = []
    for ch in str(s):
        out.append(repl.get(ch, ch))
    return "".join(out)

def compile_cover_pdf(
    out_pdf: str,
    cover_content_path: str,
    course_name: str,
    professor: str,
    exam_date: str,
    student_id: str,
    cover_title: str = "Exam paper",
) -> None:
    """
    Compile a LaTeX cover PDF that inputs `cover_content_path` as cover_content.tex.
    """
    out_pdf = str(out_pdf)
    cover_content_path = str(cover_content_path)

    # Ensure pdflatex exists
    if shutil.which("pdflatex") is None:
        raise RuntimeError(
            "pdflatex not found. Install MacTeX (or another TeX distribution) "
            "and ensure 'pdflatex' is on your PATH."
        )

    with tempfile.TemporaryDirectory(prefix="covertex_") as td:
        td_path = Path(td)

        # Copy user content into temp dir with fixed name
        shutil.copyfile(cover_content_path, td_path / "cover_content.tex")

        # Copy guidelines PDF asset if present next to the cover content
        guidelines_name = "single_choice_selection_guidelines.pdf"
        src_guidelines = Path(cover_content_path).resolve().parent / guidelines_name
        if src_guidelines.exists():
            shutil.copyfile(src_guidelines, td_path / guidelines_name)

        # Write wrapper
        tex = _LATEX_WRAPPER % {
            "course": _latex_escape(course_name),
            "prof": _latex_escape(professor),
            "date": _latex_escape(exam_date),
            "sid": _latex_escape(student_id),
            "cover_title": _latex_escape(cover_title),
        }
        (td_path / "cover_wrapper.tex").write_text(tex, encoding="utf-8")

        # Run pdflatex twice for stability (TOC etc not used, but harmless)
        cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "cover_wrapper.tex"]
        for _ in range(2):
            p = subprocess.run(cmd, cwd=str(td_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if p.returncode != 0:
                raise RuntimeError(f"LaTeX compilation failed:\n{p.stdout}")

        pdf_path = td_path / "cover_wrapper.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LaTeX compilation did not produce a PDF (cover_wrapper.pdf missing).")

        os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
        shutil.copyfile(pdf_path, out_pdf)

def merge_pdfs(out_pdf: str, pdf_paths: List[str]) -> None:
    """
    Merge PDFs in order. Uses pypdf if available, otherwise PyPDF2.
    """
    try:
        from pypdf import PdfReader, PdfWriter  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader, PdfWriter  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "PDF merge requested but neither 'pypdf' nor 'PyPDF2' is installed. "
                "Install with: pip install pypdf"
            ) from e

    writer = PdfWriter()
    for pth in pdf_paths:
        reader = PdfReader(pth)
        for page in reader.pages:
            writer.add_page(page)

    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    with open(out_pdf, "wb") as f:
        writer.write(f)

# ----------------------------
# CLI
# ----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="A4")
    ap.add_argument("--title", default="Antworten")
    ap.add_argument("--course-name", default="", help="Course name printed in header")
    ap.add_argument("--professor", default="", help="Professor name printed in header")
    ap.add_argument("--exam-date", default="", help="Exam date (defaults to today)")
    ap.add_argument("--num-questions", type=int, required=True)
    ap.add_argument("--options-per-question", default="2")
    ap.add_argument("--options-list", default=None,
                    help="Comma-separated list of option counts per question (length must equal --num-questions), e.g. 2,2,5,5,3. Overrides --options-per-question.")
    ap.add_argument("--columns", type=int, default=5)
    ap.add_argument("--force-columns", action="store_true")
    ap.add_argument("--row-gap-mm", type=float, default=0.0)
    ap.add_argument("--col-gap-mm", type=float, default=0.0)
    ap.add_argument("--box-size-mm", type=float, default=3.5,
                    help="Checkbox size in millimeters (default: 3.5mm)")
    ap.add_argument("--student-id-start", type=int, default=1)
    ap.add_argument("--student-id-count", type=int, default=1)
    ap.add_argument("--answer-key", required=True)
    ap.add_argument("--outdir", default="out")
    ap.add_argument(
        "--answer-sheet-prefix",
        default=None,
        help="Prefix to prepend to question numbers (e.g. 'A' or '1')."
    )

    # New cover-sheet flags
    ap.add_argument("--cover-tex", default=None,
                    help="Path to a LaTeX BODY file (no documentclass/begin{document}) to embed on the cover sheet.")
    ap.add_argument("--cover-title", default="Exam paper",
                    help="Label printed next to the Student-ID on the cover sheet.")
    ap.add_argument("--no-cover", action="store_true",
                    help="Disable cover sheet generation even if --cover-tex is provided.")

    # Output control
    ap.add_argument(
        "--per-student",
        action="store_true",
        help=(
            "Also keep individual PDFs per student (answer_sheet_###.pdf and cover_sheet_###.pdf). "
            "By default the script only produces combined PDFs."
        ),
    )
    ap.add_argument(
        "--keep-temp",
        action="store_true",
        help=(
            "Do not delete the intermediate per-student PDFs that are created to build the combined PDFs. "
            "(Mostly useful for debugging.)"
        ),
    )

    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    os.makedirs("scans", exist_ok=True)

    # Auto date if not provided
    if not args.exam_date:
        args.exam_date = date.today().strftime("%d. %B %Y")

    if args.options_list:
        raw = parse_csv(args.options_list)
        per_q = [int(x) for x in raw]
        if len(per_q) != args.num_questions:
            raise ValueError("--options-list must have exactly --num-questions comma-separated integers")
    else:
        per_q = parse_per_question_counts(args.options_per_question, args.num_questions)

    key_tokens = parse_answer_key(args.answer_key, args.num_questions)

    layout = compute_layout(
        args.paper, args.title, args.num_questions, per_q,
        args.columns, args.force_columns,
        args.row_gap_mm, args.col_gap_mm, args.box_size_mm
    )

    layout["answer_key"] = [
        int(tok) if tok.isdigit() else option_labels(per_q[i]).index(tok.upper())
        for i, tok in enumerate(key_tokens)
    ]

    # Optional question prefix (e.g. 'A' => labels like 'A.1')
    if args.answer_sheet_prefix is not None:
        prefix = str(args.answer_sheet_prefix).strip()
        if prefix.endswith("."):
            prefix = prefix[:-1]
        layout["question_prefix"] = prefix
    else:
        layout["question_prefix"] = ""

    # If a prefix was provided, append it to the printable title (e.g. "Title - A")
    if layout.get("question_prefix"):
        layout["title"] = f"{layout.get('title', '')} - {layout['question_prefix']}"

    # Validate answer key indices against per-question option counts
    for i, ans in enumerate(layout["answer_key"]):
        if not (0 <= int(ans) < int(per_q[i])):
            raise ValueError(f"Answer key entry for question {i+1} out of range: {ans} (options: {per_q[i]})")

    with open(os.path.join(args.outdir, "layout.json"), "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2)

    # Solution sheet
    render_sheet(
        os.path.join(args.outdir, "answer_sheet_solution.pdf"),
        layout,
        student_id=None,
        fill_solution=True,
        course_name=args.course_name,
        professor=args.professor,
        exam_date=args.exam_date,
    )

    # Student sheets + optional covers
    do_cover = (args.cover_tex is not None) and (not args.no_cover)

    if args.cover_tex is not None and not Path(args.cover_tex).exists():
        raise FileNotFoundError(f"--cover-tex not found: {args.cover_tex}")

    # We build combined PDFs by first creating per-student PDFs and then merging.
    # (This keeps the rendering functions unchanged and works well with ReportLab + LaTeX.)
    tmp_dir_ctx = tempfile.TemporaryDirectory(prefix="sheets_", dir=str(Path(args.outdir).resolve()))
    tmp_dir = Path(tmp_dir_ctx.name)

    answer_paths: List[str] = []
    cover_paths: List[str] = []

    for sid_int in range(args.student_id_start, args.student_id_start + args.student_id_count):
        sid = f"{sid_int:03d}"

        # Intermediate per-student answer sheet
        ans_pdf_tmp = tmp_dir / f"answer_sheet_{sid}.pdf"
        render_sheet(
            str(ans_pdf_tmp),
            layout,
            student_id=sid,
            fill_solution=False,
            course_name=args.course_name,
            professor=args.professor,
            exam_date=args.exam_date,
        )
        answer_paths.append(str(ans_pdf_tmp))

        # Intermediate per-student cover sheet (optional)
        if do_cover:
            cover_pdf_tmp = tmp_dir / f"cover_sheet_{sid}.pdf"
            compile_cover_pdf(
                out_pdf=str(cover_pdf_tmp),
                cover_content_path=args.cover_tex,
                course_name=args.course_name,
                professor=args.professor,
                exam_date=args.exam_date,
                student_id=sid,
                cover_title=args.cover_title,
            )
            cover_paths.append(str(cover_pdf_tmp))

        # Optionally keep per-student outputs in outdir
        if args.per_student:
            shutil.copyfile(ans_pdf_tmp, os.path.join(args.outdir, f"answer_sheet_{sid}.pdf"))
            if do_cover and cover_paths:
                shutil.copyfile(cover_paths[-1], os.path.join(args.outdir, f"cover_sheet_{sid}.pdf"))

    # Combined PDFs
    if answer_paths:
        merge_pdfs(os.path.join(args.outdir, "answer_sheets_all.pdf"), answer_paths)
    if do_cover and cover_paths:
        merge_pdfs(os.path.join(args.outdir, "cover_sheets_all.pdf"), cover_paths)

    # Cleanup intermediate files unless requested
    if args.keep_temp:
        print(f"Keeping intermediate PDFs in: {tmp_dir}")
        # Prevent automatic cleanup
        tmp_dir_ctx.cleanup = lambda *a, **k: None  # type: ignore
    else:
        tmp_dir_ctx.cleanup()

    print("Done.")

if __name__ == "__main__":
    main()
