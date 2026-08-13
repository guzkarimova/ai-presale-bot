import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database.models import Application
from schemas.presale import PresaleAnalysis
from schemas.pricing import PricingResult
from services.pricing_service import load_pricing


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "output" / "pdf"
FONT_DIR = BASE_DIR / "assets" / "fonts"


def _register_fonts() -> tuple[str, str]:
    regular = FONT_DIR / "NotoSans-Regular.ttf"
    bold = FONT_DIR / "NotoSans-Bold.ttf"
    if not regular.exists() or not bold.exists():
        raise FileNotFoundError("Noto Sans fonts are missing in assets/fonts")
    pdfmetrics.registerFont(TTFont("ProposalSans", regular))
    pdfmetrics.registerFont(TTFont("ProposalSans-Bold", bold))
    return "ProposalSans", "ProposalSans-Bold"


def _safe(text: str | None) -> str:
    return (text or "Не указано").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ProposalGenerator:
    def generate(self, application: Application, analysis: PresaleAnalysis, pricing: PricingResult) -> Path:
        logging.info("Generating PDF for application %s", application.id)
        regular, bold = _register_fonts()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"commercial_proposal_{application.id}_{datetime.now():%Y%m%d}.pdf"
        styles = getSampleStyleSheet()
        navy = colors.HexColor("#111827")
        blue = colors.HexColor("#2563EB")
        pink = colors.HexColor("#EC4899")
        pale_blue = colors.HexColor("#EFF6FF")
        pale_pink = colors.HexColor("#FDF2F8")
        body = ParagraphStyle("BodyRU", parent=styles["BodyText"], fontName=regular, fontSize=10.2, leading=15.5, textColor=colors.HexColor("#334155"), spaceAfter=7)
        heading = ParagraphStyle("HeadingRU", parent=styles["Heading2"], fontName=bold, fontSize=14.5, leading=18, textColor=navy, spaceBefore=12, spaceAfter=7)
        cover_title = ParagraphStyle("CoverTitleRU", fontName=bold, fontSize=27, leading=33, alignment=TA_LEFT, textColor=colors.white)
        cover_solution = ParagraphStyle("CoverSolutionRU", fontName=regular, fontSize=15, leading=22, alignment=TA_LEFT, textColor=colors.white)
        cover_meta = ParagraphStyle("CoverMetaRU", fontName=regular, fontSize=10.5, leading=16, alignment=TA_LEFT, textColor=colors.white)
        bullet = ParagraphStyle("BulletRU", parent=body, leftIndent=13, firstLineIndent=-9, bulletIndent=2, spaceAfter=5)
        price_style = ParagraphStyle("PriceRU", parent=body, fontName=bold, fontSize=20, leading=26, textColor=blue, alignment=TA_CENTER)

        def gradient(canvas, x, y, width, height):
            canvas.saveState()
            clip = canvas.beginPath()
            clip.rect(x, y, width, height)
            canvas.clipPath(clip, stroke=0, fill=0)
            canvas.linearGradient(x, y, x + width, y + height, (blue, pink), extend=True)
            canvas.restoreState()

        def cover(canvas, doc):
            canvas.saveState()
            gradient(canvas, 0, 0, A4[0], A4[1])
            canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.08))
            canvas.circle(178 * mm, 255 * mm, 55 * mm, stroke=0, fill=1)
            canvas.circle(25 * mm, 30 * mm, 38 * mm, stroke=0, fill=1)
            canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.18))
            canvas.roundRect(18 * mm, 270 * mm, 49 * mm, 10 * mm, 5 * mm, stroke=0, fill=1)
            canvas.setFont(bold, 8.5)
            canvas.setFillColor(colors.white)
            canvas.drawCentredString(42.5 * mm, 273.5 * mm, "AI  •  AUTOMATION")

            title_box = Paragraph("КОММЕРЧЕСКОЕ<br/>ПРЕДЛОЖЕНИЕ", cover_title)
            title_box.wrapOn(canvas, 170 * mm, 60 * mm)
            title_box.drawOn(canvas, 20 * mm, 185 * mm)
            canvas.setFillColor(colors.white)
            canvas.roundRect(20 * mm, 176 * mm, 28 * mm, 1.5 * mm, 0.7 * mm, stroke=0, fill=1)

            solution = Paragraph(
                f"Автоматизация бизнес-процесса с помощью AI:<br/><b>{_safe(analysis.recommended_solution_name)}</b>",
                cover_solution,
            )
            _, solution_height = solution.wrap(165 * mm, 58 * mm)
            solution.drawOn(canvas, 20 * mm, 160 * mm - solution_height)

            client = _safe(application.username or "название уточняется")
            meta = Paragraph(f"Клиент: <b>{client}</b><br/>Дата: {datetime.now():%d.%m.%Y}", cover_meta)
            meta.wrapOn(canvas, 165 * mm, 35 * mm)
            meta.drawOn(canvas, 20 * mm, 30 * mm)
            canvas.setFont(regular, 8)
            canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.75))
            canvas.drawRightString(190 * mm, 13 * mm, "Предварительный документ • для согласования")
            canvas.restoreState()

        def content_page(canvas, doc):
            canvas.saveState()
            gradient(canvas, 0, A4[1] - 13 * mm, A4[0], 13 * mm)
            canvas.setFont(bold, 8.5)
            canvas.setFillColor(colors.white)
            canvas.drawString(20 * mm, A4[1] - 8.5 * mm, "AI PRESALE • КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ")
            canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
            canvas.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)
            canvas.setFont(regular, 8)
            canvas.setFillColor(colors.HexColor("#7B8495"))
            canvas.drawString(20 * mm, 10 * mm, "AI Presale Assistant")
            canvas.drawRightString(190 * mm, 12 * mm, f"Страница {doc.page}")
            canvas.restoreState()

        doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=22*mm, bottomMargin=21*mm, title="Коммерческое предложение")
        story = [Spacer(1, 240 * mm), PageBreak()]

        def section_heading(name: str):
            return Table(
                [["", Paragraph(name, heading)]],
                colWidths=[3 * mm, 164 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (0, 0), pink),
                    ("BACKGROUND", (1, 0), (1, 0), pale_blue),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ("LEFTPADDING", (1, 0), (1, 0), 9),
                    ("RIGHTPADDING", (1, 0), (1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]),
            )

        def section(name: str, text: str):
            story.extend([CondPageBreak(25 * mm), section_heading(name), Spacer(1, 3 * mm), Paragraph(_safe(text), body)])

        def list_section(name: str, values: list[str]):
            values = values or ["Требуется уточнение"]
            story.extend([
                CondPageBreak(25 * mm), section_heading(name), Spacer(1, 3 * mm),
                Paragraph("• " + _safe(values[0]), bullet),
            ])
            for value in values[1:]:
                story.append(Paragraph("• " + _safe(value), bullet))

        section("1. Задача клиента", analysis.business_problem)
        section("2. Предлагаемое решение", analysis.solution_description)
        list_section("3. Как будет работать решение", analysis.proposed_workflow)
        works = [item.name for item in pricing.billable_services]
        list_section("4. Что входит в разработку", works)
        integration_lines = [
            f"{item.name} - {item.purpose}" + (". Техническая возможность и формат интеграции уточняются после анализа API/конфигурации сервиса." if item.status == "needs_check" else "")
            for item in analysis.integrations
        ]
        list_section("5. Интеграции", integration_lines)
        list_section("6. Что потребуется от клиента", analysis.required_from_client)
        list_section("7. Ожидаемый результат внедрения", analysis.expected_business_effect)
        stages = ["Анализ и уточнение процесса", "Проектирование решения", "Разработка и настройка AI"]
        if analysis.integrations:
            stages.append("Настройка и проверка интеграций")
        stages += ["Тестирование", "Запуск и стабилизация"]
        list_section("8. Этапы реализации", stages)
        section("9. Срок реализации", pricing.timeline_text + ".")
        if pricing.final_price is None:
            section("10. Стоимость проекта", "Стоимость определяется после технической оценки.")
        else:
            price_prefix = "Ориентировочная стоимость проекта - от" if pricing.manual_check_required else "Стоимость проекта"
            formatted_price = f"{pricing.final_price:,}".replace(",", " ")
            price_card = Table(
                [[Paragraph(price_prefix, body)], [Paragraph(f"{formatted_price} ₽", price_style)]],
                colWidths=[167 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), pale_pink),
                    ("BOX", (0, 0), (-1, -1), 1, pink),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]),
            )
            story.append(KeepTogether([section_heading("10. Стоимость проекта"), Spacer(1, 4 * mm), price_card]))
            if pricing.manual_check_required:
                story.append(Paragraph(
                    "Финальная стоимость модулей, требующих технической проверки, определяется после анализа конфигурации и доступных способов интеграции.",
                    body,
                ))
        support = load_pricing()["support_plans"]["basic"]
        section("11. Сопровождение", f"После запуска доступно техническое сопровождение от {support['price_month']:,} ₽/мес.".replace(",", " "))
        list_section("12. Вопросы и ограничения", analysis.clarifications_needed + analysis.risks_and_limitations)
        section("13. Важное примечание", "Коммерческое предложение является предварительным. Финальная стоимость и сроки фиксируются после согласования функционала и проверки технических возможностей необходимых интеграций.")
        section("14. Сторонние расходы", load_pricing()["third_party_costs_note"])
        doc.build(story, onFirstPage=cover, onLaterPages=content_page)
        logging.info("PDF generated for application %s: %s", application.id, path.name)
        return path
