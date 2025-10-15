from __future__ import annotations  # Styled PDF rendering for session reports

import math
import re
import textwrap
from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from fpdf import FPDF

from flow_manager.models import EvaluatorState
from .models import SessionExchange, SessionReport

try:  # pragma: no cover - backwards compatibility
    from fpdf.enums import XPos, YPos
except Exception:  # pragma: no cover - fallback for older fpdf2
    class XPos:  # type: ignore
        RIGHT = ""
        LMARGIN = ""

    class YPos:  # type: ignore
        TOP = ""
        NEXT = ""


DEJAVU_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # System font
DEJAVU_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # System font

ACCENT = (45, 115, 245)  # Palette accent
TEXT = (34, 34, 34)  # Primary text color
MUTED = (100, 100, 100)  # Secondary text color
RULE = (230, 230, 230)  # Divider color
SOFT_ACCENT_BG = (243, 248, 255)  # Highlight background


def _parse_datetime(value: str | None) -> datetime | None:  # Parse ISO timestamp safely
    if not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except Exception:  # pragma: no cover - tolerate malformed values
        return None


def _format_datetime(value: datetime | None) -> str:  # Format timestamp for display
    if not value:
        return "-"
    return value.strftime("%d %b %Y, %I:%M %p").lstrip("0").replace(" 0", " ")


def _effective_width(pdf: FPDF) -> float:  # Compute effective page width
    return float(pdf.w) - float(pdf.l_margin) - float(pdf.r_margin)


def _section_title(pdf: FPDF, title: str) -> None:  # Render styled section title
    pdf.set_text_color(*TEXT)
    pdf.set_x(pdf.l_margin)
    pdf.set_font(pdf._font_bold, "B", 13)
    try:
        pdf.cell(0, 9, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    except TypeError:
        pdf.cell(0, 9, title, ln=1)
    pdf.set_draw_color(*RULE)
    pdf.set_line_width(0.2)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + _effective_width(pdf), y)
    pdf.ln(2)


def _meta_block(pdf: FPDF, rows: List[Tuple[str, str]]) -> None:  # Draw two-column metadata
    width = _effective_width(pdf)
    col = width / 2.0
    line = 6
    for idx in range(0, len(rows), 2):
        left = rows[idx]
        right = rows[idx + 1] if idx + 1 < len(rows) else ("", "")
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 10)
        try:
            pdf.cell(col, line, left[0], new_x=XPos.RIGHT, new_y=YPos.TOP)
        except TypeError:
            pdf.cell(col, line, left[0], ln=0)
        try:
            pdf.cell(col, line, right[0], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        except TypeError:
            pdf.cell(col, line, right[0], ln=1)
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*TEXT)
        pdf.set_font(pdf._font_bold, "B", 11)
        try:
            pdf.cell(col, line, left[1], new_x=XPos.RIGHT, new_y=YPos.TOP)
        except TypeError:
            pdf.cell(col, line, left[1], ln=0)
        try:
            pdf.cell(col, line, right[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        except TypeError:
            pdf.cell(col, line, right[1], ln=1)
    pdf.ln(2)


def _score_value(value: float | None) -> str:  # Format score for display
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except Exception:
        return str(value)
    if numeric <= 5:
        return f"{numeric:.2f}/5"
    return f"{numeric:.1f}/10"


def _calc_text_height(pdf: FPDF, width: float, text: str, line_height: float) -> float:  # Estimate multi-cell height
    if not text:
        return line_height
    try:
        lines = pdf.multi_cell(width, line_height, text, dry_run=True, output="LINES")
        if isinstance(lines, (list, tuple)):
            return line_height * max(1, len(lines))
    except TypeError:
        try:
            lines = pdf.multi_cell(width, line_height, text, split_only=True)
            if isinstance(lines, (list, tuple)):
                return line_height * max(1, len(lines))
        except TypeError:
            pass
    approx = max(1, math.ceil(len(text) / 90))
    return approx * line_height


class ReportPDF(FPDF):  # PDF with custom header/footer styling
    def __init__(self, *args, accent: Tuple[int, int, int] = ACCENT, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.accent = accent
        self.header_title = "Interview Report"
        self._font_regular = "Helvetica"
        self._font_bold = "Helvetica"
        self._supports_unicode = False

    def _prepare_text(self, text: Any) -> str:  # Sanitize text for non-unicode fonts
        value = "" if text is None else str(text)
        if self._supports_unicode:
            return value
        cleaned = value.replace("•", "-")
        try:
            return cleaned.encode("latin-1", "ignore").decode("latin-1")
        except Exception:
            return cleaned

    def cell(self, *args, **kwargs):  # Wrap base cell with text sanitisation
        args_list = list(args)
        if len(args_list) >= 3:
            args_list[2] = self._prepare_text(args_list[2])
        elif "text" in kwargs:
            kwargs["text"] = self._prepare_text(kwargs["text"])
        elif "txt" in kwargs:
            kwargs["txt"] = self._prepare_text(kwargs["txt"])
        return super().cell(*args_list, **kwargs)

    def multi_cell(self, *args, **kwargs):  # Wrap base multi_cell with text sanitisation
        args_list = list(args)
        if len(args_list) >= 3:
            args_list[2] = self._prepare_text(args_list[2])
        elif "text" in kwargs:
            kwargs["text"] = self._prepare_text(kwargs["text"])
        elif "txt" in kwargs:
            kwargs["txt"] = self._prepare_text(kwargs["txt"])
        return super().multi_cell(*args_list, **kwargs)

    def header(self) -> None:  # Render header banner
        usable = _effective_width(self)
        if self.page_no() == 1:
            line_height = 8
            self.set_font(self._font_bold, "B", 16)
            lines = 1
            try:
                trial = self.multi_cell(usable, line_height, self.header_title, dry_run=True, output="LINES")
                if isinstance(trial, (list, tuple)):
                    lines = len(trial)
            except TypeError:
                try:
                    trial = self.multi_cell(usable, line_height, self.header_title, split_only=True)
                    if isinstance(trial, (list, tuple)):
                        lines = len(trial)
                except TypeError:
                    lines = 1
            banner = 6 + lines * line_height + 4
            self.set_fill_color(*self.accent)
            self.rect(0, 0, self.w, banner, style="F")
            self.set_text_color(255, 255, 255)
            self.set_xy(self.l_margin, 6)
            self.multi_cell(usable, line_height, self.header_title)
            self.set_text_color(*TEXT)
            self.ln(4)
        else:
            self.set_text_color(80, 80, 80)
            self.set_xy(self.l_margin, 8)
            self.set_font(self._font_bold, "B", 12)
            self.multi_cell(usable, 6, self.header_title)
            mark = self.get_y()
            self.set_draw_color(*self.accent)
            self.set_line_width(0.4)
            self.line(self.l_margin, mark + 1, self.w - self.r_margin, mark + 1)
            self.set_text_color(*TEXT)
            self.ln(4)

    def footer(self) -> None:  # Render footer with pagination
        self.set_y(-12)
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_text_color(120, 120, 120)
        self.set_font(self._font_regular, "", 9)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="R")


def _summarize(text: str) -> str:  # Summarize longer paragraphs
    cleaned = " ".join(text.split()) if text else ""
    if not cleaned:
        return "-"
    segments = [seg.strip() for seg in re.split(r"(?<=[.!?])\s+", cleaned) if seg.strip()]
    snippet = " ".join(segments[:3]) or cleaned
    return textwrap.shorten(snippet, width=380, placeholder="…")


def _render_llm_section(pdf: FPDF, llms: Sequence[Tuple[str, str, str]]) -> None:  # Render LLM usage bullets
    bullet = "•" if getattr(pdf, "_font_regular", "") == "DejaVu" else "-"
    if not llms:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 11)
        pdf.multi_cell(_effective_width(pdf), 6, "LLM configuration unavailable for this session.")
        pdf.ln(2)
        pdf.set_text_color(*TEXT)
        return
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*TEXT)
    pdf.set_font(pdf._font_regular, "", 11)
    for module, route, model in llms:
        label = module.split(".")[-1].replace("_", " ").title()
        pdf.multi_cell(
            _effective_width(pdf),
            6,
            f"{bullet} {label}: {route} ({model})",
        )
    pdf.ln(2)


def _collect_latest_evaluator(exchanges: Sequence[SessionExchange]) -> EvaluatorState | None:  # Get last evaluator state
    latest: EvaluatorState | None = None
    for entry in exchanges:
        latest = entry.evaluator
    return latest


def _render_competency_table(pdf: FPDF, evaluator: EvaluatorState | None) -> float | None:  # Draw competency scores table
    headers = ["Competency", "Score", "Notes", "Updates"]
    widths = [
        _effective_width(pdf) * 0.2,
        _effective_width(pdf) * 0.13,
        _effective_width(pdf) * 0.33,
        _effective_width(pdf) * 0.34,
    ]
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*ACCENT)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(pdf._font_bold, "B", 10)
    for idx, title in enumerate(headers):
        try:
            pdf.cell(widths[idx], 8, title, align="L", fill=True)
        except TypeError:
            pdf.cell(widths[idx], 8, title, align="L")
    pdf.ln(8)
    pdf.set_text_color(*TEXT)
    if evaluator is None or not evaluator.scores:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 10)
        pdf.multi_cell(_effective_width(pdf), 6, "No competency scores recorded yet.")
        pdf.set_text_color(*TEXT)
        pdf.ln(4)
        return None
    pdf.set_font(pdf._font_regular, "", 10)
    total = 0.0
    count = 0
    for idx, (name, score) in enumerate(evaluator.scores.items()):
        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(247, 250, 255)
        pdf.set_x(pdf.l_margin)
        pdf.cell(widths[0], 7, name, border=0, fill=fill)
        pdf.cell(widths[1], 7, _score_value(score.score), border=0, fill=fill)
        notes = "; ".join(score.notes) or "-"
        pdf.cell(widths[2], 7, notes, border=0, fill=fill)
        updates = "; ".join(score.rubric_updates) or "-"
        pdf.cell(widths[3], 7, updates, border=0, fill=fill)
        pdf.ln(7)
        total += score.score
        count += 1
    pdf.ln(2)
    return total / count if count else None


def _render_criterion_table(pdf: FPDF, evaluator: EvaluatorState | None) -> None:  # Draw criterion level table
    headers = ["Competency", "Criterion", "Level"]
    widths = [
        _effective_width(pdf) * 0.28,
        _effective_width(pdf) * 0.48,
        _effective_width(pdf) * 0.24,
    ]
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*ACCENT)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(pdf._font_bold, "B", 10)
    for idx, title in enumerate(headers):
        try:
            pdf.cell(widths[idx], 8, title, align="L", fill=True)
        except TypeError:
            pdf.cell(widths[idx], 8, title, align="L")
    pdf.ln(8)
    pdf.set_text_color(*TEXT)
    if evaluator is None or not evaluator.scores:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 10)
        pdf.multi_cell(_effective_width(pdf), 6, "No criterion-level feedback recorded yet.")
        pdf.set_text_color(*TEXT)
        pdf.ln(4)
        return
    rows: List[Tuple[str, str, str]] = []
    for name, score in evaluator.scores.items():
        for criterion, level in score.criterion_levels.items():
            rows.append((name, criterion, str(level)))
    if not rows:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 10)
        pdf.multi_cell(_effective_width(pdf), 6, "No criterion-level feedback recorded yet.")
        pdf.set_text_color(*TEXT)
        pdf.ln(4)
        return
    pdf.set_font(pdf._font_regular, "", 10)
    for idx, row in enumerate(rows):
        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(247, 250, 255)
        pdf.set_x(pdf.l_margin)
        pdf.cell(widths[0], 7, row[0], border=0, fill=fill)
        pdf.cell(widths[1], 7, row[1], border=0, fill=fill)
        pdf.cell(widths[2], 7, row[2], border=0, align="C", fill=fill)
        pdf.ln(7)
    pdf.ln(2)


def _transcript_widths(pdf: FPDF) -> Tuple[float, float, float]:  # Compute transcript column widths
    total = _effective_width(pdf)
    gap = 6.0
    primary = max(total * 0.64, total - 120)
    secondary = total - primary - gap
    if secondary < total * 0.22:
        secondary = total * 0.22
        primary = total - secondary - gap
    return primary, secondary, gap


def _format_entry_details(entry: SessionExchange) -> List[str]:  # Build highlight lines for transcript
    details: List[str] = []
    stage = entry.stage or "warmup"
    details.append(f"Stage: {stage.title()}")
    if entry.competency:
        details.append(f"Competency: {entry.competency}")
    if entry.criteria:
        details.append("Criteria: " + ", ".join(entry.criteria))
    anchors = entry.evaluator.anchors.get(stage, [])
    for anchor in anchors:
        details.append(f"Anchor: {anchor}")
    if entry.competency:
        score = entry.evaluator.scores.get(entry.competency)
        if score:
            details.append(f"Score: {_score_value(score.score)}")
            for name, level in score.criterion_levels.items():
                details.append(f"{name}: Level {level}")
    return details


def _render_transcript_header(pdf: FPDF, left: float, right: float, gap: float) -> None:  # Render transcript header row
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*ACCENT)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(pdf._font_bold, "B", 10)
    try:
        pdf.cell(left, 8, "Dialogue", align="L", fill=True)
        pdf.cell(gap, 8, "", fill=True)
        pdf.cell(right, 8, "Highlights", align="L", fill=True)
    except TypeError:
        pdf.cell(left, 8, "Dialogue", align="L")
        pdf.cell(gap, 8, "")
        pdf.cell(right, 8, "Highlights", align="L")
    pdf.ln(8)
    pdf.set_text_color(*TEXT)


def _render_transcript_row(pdf: FPDF, left: float, right: float, gap: float, entry: SessionExchange) -> None:  # Render Q&A row
    line = 5.5
    bullet = "•" if getattr(pdf, "_font_regular", "") == "DejaVu" else "-"
    question = f"Q: {(entry.question or '-').strip()}"
    answer = f"A: {(entry.answer or '-').strip()}"
    system = entry.system_message.strip()
    details = _format_entry_details(entry)
    highlight = "\n".join(f"{bullet} {item}" for item in details)
    text_height = _calc_text_height(pdf, left, question, line) + _calc_text_height(pdf, left, answer, line)
    if system:
        text_height += _calc_text_height(pdf, left, f"System: {system}", line)
    highlight_height = _calc_text_height(pdf, right, highlight, line)
    block = max(text_height, highlight_height) + 6
    if pdf.get_y() + block > pdf.page_break_trigger:
        pdf.add_page()
        _render_transcript_header(pdf, left, right, gap)
    origin_x = pdf.l_margin
    origin_y = pdf.get_y()
    pdf.set_fill_color(248, 249, 255)
    pdf.rect(origin_x, origin_y, left, block, style="F")
    pdf.set_xy(origin_x + 2, origin_y + 2)
    pdf.set_text_color(*ACCENT)
    pdf.set_font(pdf._font_bold, "B", 10)
    pdf.multi_cell(left - 4, line, question)
    pdf.set_x(origin_x + 2)
    pdf.set_text_color(60, 60, 60)
    pdf.set_font(pdf._font_regular, "", 10)
    pdf.multi_cell(left - 4, line, answer)
    if system:
        pdf.set_x(origin_x + 2)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 9)
        pdf.multi_cell(left - 4, line, f"System: {system}")
    pdf.set_xy(origin_x + left + gap, origin_y + 2)
    if details:
        pdf.set_text_color(*ACCENT)
        pdf.set_font(pdf._font_bold, "B", 9)
        pdf.multi_cell(right, line, details[0])
        for extra in details[1:]:
            pdf.set_x(origin_x + left + gap)
            pdf.set_text_color(*TEXT)
            pdf.set_font(pdf._font_regular, "", 9)
            pdf.multi_cell(right, line, f"{bullet} {extra}")
    else:
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 9)
        pdf.multi_cell(right, line, "No highlights captured.")
    bottom = max(pdf.get_y(), origin_y + block - 2)
    pdf.set_draw_color(*RULE)
    pdf.set_line_width(0.2)
    pdf.line(origin_x, bottom + 1, origin_x + left + gap + right, bottom + 1)
    pdf.set_y(bottom + 4)
    pdf.set_text_color(*TEXT)


def _render_transcript(pdf: FPDF, exchanges: Sequence[SessionExchange]) -> None:  # Render transcript section
    left, right, gap = _transcript_widths(pdf)
    _render_transcript_header(pdf, left, right, gap)
    if not exchanges:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 10)
        pdf.multi_cell(_effective_width(pdf), 6, "No transcript entries recorded for this session.")
        pdf.set_text_color(*TEXT)
        pdf.ln(4)
        return
    for entry in exchanges:
        _render_transcript_row(pdf, left, right, gap, entry)


def _rubric_summary(rubric: SessionReport) -> Iterable[str]:  # Yield rubric summaries
    for block in rubric.rubric.rubrics:
        yield f"{block.competency}: band {block.band}, pass >= {block.min_pass_score:.1f}"


def generate_session_report_pdf(  # Build PDF payload for a session report
    report: SessionReport,
    llms: Sequence[Tuple[str, str, str]],
) -> bytes:
    pdf = ReportPDF()
    pdf.alias_nb_pages()
    try:
        pdf.add_font("DejaVu", "", DEJAVU_SANS)
        pdf.add_font("DejaVu", "B", DEJAVU_SANS_BOLD)
        pdf._font_regular = "DejaVu"
        pdf._font_bold = "DejaVu"
        pdf._supports_unicode = True
    except Exception:  # pragma: no cover - font registration optional
        pdf._font_regular = "Helvetica"
        pdf._font_bold = "Helvetica"
        pdf._supports_unicode = False
    pdf.header_title = f"{report.job_title} - {report.candidate_name} - Evaluation Report"
    pdf.set_margins(15, 22, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    created = _parse_datetime(report.created_at)
    updated = _parse_datetime(report.updated_at)

    _section_title(pdf, "LLMs Used")
    _render_llm_section(pdf, llms)

    _section_title(pdf, "Session Overview")
    overview_rows = [
        ("Interview ID", report.interview_id),
        ("Candidate ID", report.candidate_id),
        ("Candidate", report.candidate_name),
        ("Role", report.job_title),
        ("Created", _format_datetime(created)),
        ("Updated", _format_datetime(updated)),
    ]
    _meta_block(pdf, overview_rows)

    _section_title(pdf, "Rubric Summary")
    pdf.set_x(pdf.l_margin)
    pdf.set_font(pdf._font_regular, "", 11)
    pdf.set_text_color(*TEXT)
    for line in _rubric_summary(report):
        pdf.multi_cell(_effective_width(pdf), 6, f"• {line}")
    pdf.ln(2)

    evaluator = _collect_latest_evaluator(report.exchanges)
    overall = _render_competency_table(pdf, evaluator)

    _section_title(pdf, "Criterion Levels")
    _render_criterion_table(pdf, evaluator)

    if overall is not None:
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(*SOFT_ACCENT_BG)
        pdf.set_draw_color(225, 232, 248)
        pdf.rect(pdf.l_margin, pdf.get_y(), _effective_width(pdf), 16, style="F")
        pdf.set_xy(pdf.l_margin + 6, pdf.get_y() + 4)
        pdf.set_text_color(*MUTED)
        pdf.set_font(pdf._font_regular, "", 10)
        pdf.cell(_effective_width(pdf) - 12, 6, "Overall Average Score")
        pdf.set_xy(pdf.l_margin, pdf.get_y() - 2)
        pdf.set_text_color(*ACCENT)
        pdf.set_font(pdf._font_bold, "B", 14)
        pdf.cell(_effective_width(pdf) - 6, 8, _score_value(overall), align="R")
        pdf.ln(12)
        pdf.set_text_color(*TEXT)

    _section_title(pdf, "Question & Answer Transcript")
    _render_transcript(pdf, report.exchanges)

    output = pdf.output(dest="S")
    if isinstance(output, bytearray):
        output = bytes(output)
    return output if isinstance(output, bytes) else output.encode("latin-1")


__all__ = ["generate_session_report_pdf"]
