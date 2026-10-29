"""Converte o relatório existente em PDF com quatro figuras em páginas paisagem.

Requer reportlab e Pillow. Não recalcula dados ou modifica o relatório fonte.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

HERE = Path(__file__).resolve().parent / "representatividade"
SOURCE = HERE / "relatorio.md"
TARGET = HERE / "relatorio-representatividade-risco-v4.pdf"
GREEN = colors.HexColor("#173F35")
INK = colors.HexColor("#273A34")
CAPTIONS = {
    "exemplo_distribuicao.png": "Distribuição dos 28.560 pixels do grupo citado, com média, mediana e P75. Muito alto ocupa 48,28%; Alto e Muito alto juntos ocupam 58,68%.",
    "distribuicoes_estaduais.png": "Distribuições empíricas estaduais dos escores e dos percentis. O eixo do escore é não linear; os percentis expressam posição relativa e não probabilidade de incêndio.",
    "distribuicao_pixels_e_grupos.png": "Comparação da composição dos pixels originais com a cobertura das cores dos grupos agregados. As barras hachuradas atribuem a cor do grupo a todos os seus pixels.",
    "comparacao_mapas_2026_random_forest.png": "Comparação da classe da média, classe predominante, classe da mediana e concentração de pixels Alto + Muito alto. A concentração tem escala própria de porcentagem dos pixels, diferente das classes dos outros três mapas.",
}


def blocks(text):
    lines = text.splitlines()
    i = 0
    start = re.compile(r"^(?:#{1,3} |\| |!\[|```|- |\d+\. )")
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            yield "code", "\n".join(code)
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            yield "table", rows
            continue
        elif match := re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", line):
            yield "image", match.groups()
        elif line.startswith("# "):
            yield "title", line[2:]
        elif line.startswith("## "):
            yield "heading", line[3:]
        else:
            kind = "bullet" if line.startswith("- ") else "body"
            if kind == "bullet":
                line = "• " + line[2:]
            paragraph = [line]
            while i + 1 < len(lines) and lines[i+1].strip() and not start.match(lines[i+1].strip()):
                i += 1
                paragraph.append(lines[i].strip())
            yield kind, " ".join(paragraph)
        i += 1


def rich(text):
    text = html.escape(text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<link href="\2" color="#245F88">\1</link>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`([^`]+)`", r'<font name="Mono" size="8">\1</font>', text)


def decorations(canvas, doc):
    width, height = canvas._pagesize
    canvas.saveState()
    canvas.setFillColor(GREEN)
    canvas.setFont("Body-Bold", 8)
    canvas.drawString(18*mm, height-12*mm, "INCENDIOFLORESTA  /  REPRESENTATIVIDADE DO RISCO V4")
    canvas.setStrokeColor(colors.HexColor("#D2DFD7"))
    canvas.line(18*mm, height-15*mm, width-18*mm, height-15*mm)
    canvas.setFont("Body", 7)
    canvas.setFillColor(colors.HexColor("#65776F"))
    canvas.drawString(18*mm, 11*mm, "Produtos de 2025 e 2026 · Estudo descritivo da agregação espacial")
    canvas.drawRightString(width-18*mm, 11*mm, f"Página {doc.page}")
    canvas.restoreState()


def main():
    fonts = Path("/usr/share/fonts/truetype/dejavu")
    for name, filename in (("Body","DejaVuSans.ttf"),("Body-Bold","DejaVuSans-Bold.ttf"),
                           ("Body-Italic","DejaVuSans-Oblique.ttf"),("Mono","DejaVuSansMono.ttf")):
        pdfmetrics.registerFont(TTFont(name,str(fonts/filename)))
    pdfmetrics.registerFontFamily("Body",normal="Body",bold="Body-Bold",italic="Body-Italic",boldItalic="Body-Bold")
    styles = {
        "body": ParagraphStyle("body",fontName="Body",fontSize=9.5,leading=14,spaceAfter=8,textColor=INK,allowWidows=0,allowOrphans=0),
        "title": ParagraphStyle("title",fontName="Body-Bold",fontSize=24,leading=30,spaceAfter=18,textColor=GREEN,keepWithNext=True),
        "heading": ParagraphStyle("heading",fontName="Body-Bold",fontSize=14,leading=19,spaceBefore=14,spaceAfter=9,textColor=GREEN,keepWithNext=True),
        "cell": ParagraphStyle("cell",fontName="Body",fontSize=8,leading=11,textColor=INK,splitLongWords=True),
        "header": ParagraphStyle("header",fontName="Body-Bold",fontSize=8,leading=11,textColor=colors.white),
        "caption": ParagraphStyle("caption",fontName="Body",fontSize=9,leading=13,textColor=INK,spaceBefore=8,spaceAfter=8),
        "code": ParagraphStyle("code",fontName="Mono",fontSize=8,leading=12,textColor=INK,backColor=colors.HexColor("#F0F5F2"),borderPadding=7,spaceAfter=12),
    }
    styles["bullet"] = ParagraphStyle("bullet",parent=styles["body"],leftIndent=10,firstLineIndent=-8,spaceAfter=5)
    doc = BaseDocTemplate(str(TARGET),pagesize=A4,title="Representatividade da agregação do Risco v4 em grupos de 5 km",
                          author="Projeto IncendioFloresta",subject="Média, moda, mediana, P75 e concentração de pixels altos")
    for name,size in (("portrait",A4),("landscape",landscape(A4))):
        width,height=size
        frame=Frame(18*mm,20*mm,width-36*mm,height-42*mm,id=name,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        doc.addPageTemplates(PageTemplate(id=name,frames=[frame],pagesize=size,onPage=decorations))
    figures = []
    story = []
    for kind,value in blocks(SOURCE.read_text()):
        if kind == "image":
            alt,filename=value
            path=HERE/filename
            if not path.is_file():raise FileNotFoundError(path)
            figures.append((alt,path))
            number=len(figures)
            story.append(Paragraph(f'<link href="#figure{number}" color="#245F88"><b>Figura {number} — {html.escape(alt)}.</b> Ver comparação visual no anexo.</link>',styles["caption"]))
        elif kind == "table":
            count=len(value[0]);weights={3:[.40,.25,.35],4:[.31,.20,.20,.29]}.get(count,[1/count]*count)
            cells=[[Paragraph(rich(cell),styles["header" if row==0 else "cell"]) for cell in cells] for row,cells in enumerate(value)]
            table=Table(cells,colWidths=[(A4[0]-36*mm)*w for w in weights],repeatRows=1,hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),GREEN),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F0F5F2"),colors.white]),
                ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),
                ("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),
                ("BOTTOMPADDING",(0,0),(-1,-1),5),("LINEBELOW",(0,1),(-1,-1),.3,colors.HexColor("#D2DFD7"))]))
            story.extend([table,Spacer(1,10)])
        elif kind == "code":
            story.append(Paragraph(html.escape(value).replace("\n","<br/>"),styles["code"]))
        else:
            story.append(Paragraph(rich(value),styles[kind]))
    assert len(figures)==4
    story.extend([NextPageTemplate("landscape"),PageBreak()])
    for number,(alt,path) in enumerate(figures,1):
        if number>1:story.append(PageBreak())
        story.append(Paragraph(f'<a name="figure{number}"/>Figura {number} — {html.escape(alt)}',styles["heading"]))
        with PILImage.open(path) as image:
            width,height=image.size
        scale=min((landscape(A4)[0]-36*mm)/width,(landscape(A4)[1]-80*mm)/height)
        story.append(Image(str(path),width=width*scale,height=height*scale))
        story.append(Paragraph(html.escape(CAPTIONS[path.name]),styles["caption"]))
    doc.build(story)
    print(f"PDF gerado com {len(figures)} figuras: {TARGET}")


if __name__=="__main__":
    main()
