from __future__ import annotations  # PDF rendering for interview rubrics

from typing import Iterable

from fpdf import FPDF

from .rubric_design import InterviewRubricSnapshot, Rubric, RubricCriterion

TEXT = (36, 44, 61)
MUTED = (110, 118, 135)
RULE = (206, 214, 229)
SOFT_BG = (241, 245, 252)
DEJAVU_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class RubricPDF(FPDF):  # Minimal PDF subclass for rubric export
    def __init__(self) -> None:  # Initialize base fonts and settings
        super().__init__(orientation="P", unit="mm", format="A4")
        self.header_title = ""
        self._font_regular = "Helvetica"
        self._font_bold = "Helvetica"
        self._supports_unicode = False

    def header(self) -> None:  # Render page header
        if not self.header_title:
            return
        self.set_text_color(*TEXT)
        self.set_font(self._font_bold, "B", 14)
        self.cell(0, 8, self.header_title, ln=1)
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self) -> None:  # Render page footer
        self.set_y(-15)
        self.set_text_color(*MUTED)
        self.set_font(self._font_regular, "", 9)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="R")

    def _prepare_text(self, text: object) -> str:  # Coerce text for non-unicode fonts
        value = "" if text is None else str(text)
        if self._supports_unicode:
            return value
        cleaned = (
            value.replace("’", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("—", "-")
            .replace("•", "-")
        )
        try:
            return cleaned.encode("latin-1", "ignore").decode("latin-1")
        except Exception:
            return cleaned

    def cell(self, *args, **kwargs):  # Sanitize text before rendering cell
        args_list = list(args)
        if len(args_list) >= 3:
            args_list[2] = self._prepare_text(args_list[2])
        if "text" in kwargs:
            kwargs["text"] = self._prepare_text(kwargs["text"])
        if "txt" in kwargs:
            kwargs["txt"] = self._prepare_text(kwargs["txt"])
        return super().cell(*args_list, **kwargs)

    def multi_cell(self, *args, **kwargs):  # Sanitize text before multi-cell
        args_list = list(args)
        if len(args_list) >= 3:
            args_list[2] = self._prepare_text(args_list[2])
        if "text" in kwargs:
            kwargs["text"] = self._prepare_text(kwargs["text"])
        if "txt" in kwargs:
            kwargs["txt"] = self._prepare_text(kwargs["txt"])
        return super().multi_cell(*args_list, **kwargs)


def generate_rubric_pdf(snapshot: InterviewRubricSnapshot) -> bytes:  # Render rubric snapshot to PDF
    pdf = RubricPDF()
    pdf.set_margins(16, 20, 16)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.alias_nb_pages()
    try:
        pdf.add_font("DejaVu", "", DEJAVU_SANS)
        pdf.add_font("DejaVu", "B", DEJAVU_SANS_BOLD)
        pdf._font_regular = "DejaVu"
        pdf._font_bold = "DejaVu"
        pdf._supports_unicode = True
    except Exception:
        pdf._font_regular = "Helvetica"
        pdf._font_bold = "Helvetica"
        pdf._supports_unicode = False
    pdf.header_title = f"{snapshot.job_title} Interview Rubric"
    pdf.add_page()
    _render_overview(pdf, snapshot)
    for rubric in snapshot.rubrics:
        _render_rubric(pdf, rubric)
    output = pdf.output(dest="S")
    if isinstance(output, bytearray):
        output = bytes(output)
    return output if isinstance(output, bytes) else output.encode("latin-1")


def _render_overview(pdf: RubricPDF, snapshot: InterviewRubricSnapshot) -> None:  # Render interview overview block
    _section_title(pdf, "Role Overview")
    rows = [
        ("Interview ID", snapshot.interview_id),
        ("Job Title", snapshot.job_title),
        ("Experience", snapshot.experience_years),
        ("Status", snapshot.status or "ready"),
    ]
    _meta_rows(pdf, rows)
    description = snapshot.job_description.strip()
    if description:
        _section_title(pdf, "Job Description")
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*TEXT)
        pdf.set_font(pdf._font_regular, "", 11)
        pdf.multi_cell(_effective_width(pdf), 6, description)
        pdf.ln(2)


def _render_rubric(pdf: RubricPDF, rubric: Rubric) -> None:  # Render rubric section
    label = f"{rubric.competency} (Band {rubric.band})"
    _section_title(pdf, label)
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*TEXT)
    pdf.set_font(pdf._font_regular, "", 11)
    pdf.cell(0, 6, f"Minimum passing score {rubric.min_pass_score:.1f}", ln=1)
    if rubric.band_notes:
        _subheading(pdf, "Band Notes")
        _bullet_list(pdf, rubric.band_notes)
    _render_criteria(pdf, rubric.criteria)
    if rubric.evidence:
        _subheading(pdf, "Suggested Probes")
        _bullet_list(pdf, rubric.evidence)
    if rubric.red_flags:
        _subheading(pdf, "Red Flags")
        _bullet_list(pdf, rubric.red_flags)
    pdf.ln(4)


def _render_criteria(pdf: RubricPDF, criteria: Iterable[RubricCriterion]) -> None:  # Render criteria with anchors
    for criterion in criteria:
        name = f"{criterion.name} (weight {criterion.weight:.2f})"
        _subheading(pdf, name)
        anchors = sorted(criterion.anchors, key=lambda item: item.level)
        for anchor in anchors:
            text = f"Level {anchor.level}: {anchor.text}"
            _bullet_line(pdf, text, indent=6)
        pdf.ln(1)


def _section_title(pdf: RubricPDF, title: str) -> None:  # Render section title with rule
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*SOFT_BG)
    pdf.set_draw_color(*RULE)
    pdf.set_text_color(*TEXT)
    pdf.set_font(pdf._font_bold, "B", 12)
    pdf.cell(_effective_width(pdf), 8, title, ln=1, fill=True)
    pdf.ln(2)


def _subheading(pdf: RubricPDF, title: str) -> None:  # Render subsection heading
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*TEXT)
    pdf.set_font(pdf._font_bold, "B", 11)
    pdf.cell(0, 6, title, ln=1)
    pdf.ln(1)


def _bullet_list(pdf: RubricPDF, items: Iterable[str]) -> None:  # Render bullet list
    for item in items:
        _bullet_line(pdf, item, indent=4)
    pdf.ln(1)


def _bullet_line(pdf: RubricPDF, text: str, *, indent: float) -> None:  # Render single bullet line
    pdf.set_x(pdf.l_margin + indent)
    pdf.set_text_color(*TEXT)
    pdf.set_font(pdf._font_regular, "", 10)
    pdf.multi_cell(_effective_width(pdf) - indent, 5, f"- {text}")


def _meta_rows(pdf: RubricPDF, rows: Iterable[tuple[str, str]]) -> None:  # Render key-value rows
    width = _effective_width(pdf)
    label_width = width * 0.3
    for label, value in rows:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 9)
        pdf.cell(label_width, 5, label.upper())
        pdf.set_text_color(*TEXT)
        pdf.set_font(pdf._font_bold, "B", 11)
        pdf.multi_cell(width - label_width, 6, value or "-")
        pdf.ln(1)
    pdf.ln(2)


def _effective_width(pdf: RubricPDF) -> float:  # Compute effective content width
    return float(pdf.w) - float(pdf.l_margin) - float(pdf.r_margin)


__all__ = ["generate_rubric_pdf"]
