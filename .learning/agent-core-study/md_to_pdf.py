#!/usr/bin/env python3
"""
Markdown to PDF converter using markdown library and reportlab
"""
import markdown
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import sys
import os
from pathlib import Path

def create_styles():
    """Create custom styles for markdown elements"""
    styles = getSampleStyleSheet()

    # Title style
    styles.add(ParagraphStyle(
        name='MarkdownTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor='#000000'
    ))

    # Heading 1
    styles.add(ParagraphStyle(
        name='MarkdownH1',
        parent=styles['Heading1'],
        fontSize=20,
        spaceBefore=20,
        spaceAfter=10,
        textColor='#333333'
    ))

    # Heading 2
    styles.add(ParagraphStyle(
        name='MarkdownH2',
        parent=styles['Heading2'],
        fontSize=16,
        spaceBefore=15,
        spaceAfter=8,
        textColor='#444444'
    ))

    # Heading 3
    styles.add(ParagraphStyle(
        name='MarkdownH3',
        parent=styles['Heading3'],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=6,
        textColor='#555555'
    ))

    # Normal text
    styles.add(ParagraphStyle(
        name='MarkdownText',
        parent=styles['Normal'],
        fontSize=11,
        spaceBefore=6,
        spaceAfter=6,
        leading=14
    ))

    # Code block
    styles.add(ParagraphStyle(
        name='MarkdownCode',
        parent=styles['Code'],
        fontSize=9,
        spaceBefore=8,
        spaceAfter=8,
        leftIndent=20,
        rightIndent=20,
        backColor='#f5f5f5',
        textColor='#333333'
    ))

    # Blockquote
    styles.add(ParagraphStyle(
        name='MarkdownQuote',
        parent=styles['Normal'],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=10,
        leftIndent=30,
        textColor='#666666',
        borderColor='#999999',
        borderWidth=1,
        borderPadding=5
    ))

    return styles

def parse_markdown_line_by_line(md_text, styles):
    """Parse markdown line by line and convert to reportlab elements"""
    elements = []
    lines = md_text.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]

        # Empty line
        if not line.strip():
            elements.append(Spacer(1, 6))
            i += 1
            continue

        # Title (first # heading)
        if line.startswith('# ') and not elements:
            text = line[2:].strip()
            elements.append(Paragraph(text, styles['MarkdownTitle']))
            i += 1
            continue

        # Heading 1
        if line.startswith('# '):
            text = line[2:].strip()
            elements.append(Paragraph(text, styles['MarkdownH1']))
            i += 1
            continue

        # Heading 2
        if line.startswith('## '):
            text = line[3:].strip()
            elements.append(Paragraph(text, styles['MarkdownH2']))
            i += 1
            continue

        # Heading 3
        if line.startswith('### '):
            text = line[4:].strip()
            elements.append(Paragraph(text, styles['MarkdownH3']))
            i += 1
            continue

        # Code block
        if line.strip().startswith('```'):
            code_lines = []
            i += 1  # Skip the opening ```
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1

            # Join code lines and preserve formatting
            code_text = '\n'.join(code_lines)
            # Use Preformatted for code blocks
            elements.append(Preformatted(code_text, styles['MarkdownCode']))
            i += 1  # Skip the closing ```
            continue

        # Blockquote
        if line.startswith('>'):
            text = line[1:].strip()
            # Remove the > and parse inner markdown
            if text.startswith(' '):
                text = text[1:]
            elements.append(Paragraph(text, styles['MarkdownQuote']))
            i += 1
            continue

        # Horizontal rule
        if line.strip() == '---':
            elements.append(Spacer(1, 20))
            i += 1
            continue

        # Table (simple detection)
        if '|' in line and i + 1 < len(lines) and '|' in lines[i + 1]:
            # Collect table rows
            table_lines = [line]
            i += 1
            while i < len(lines) and '|' in lines[i]:
                table_lines.append(lines[i])
                i += 1

            # Parse table
            table_text = '\n'.join(table_lines)
            # Render as code block for now (tables are complex in reportlab)
            elements.append(Preformatted(table_text, styles['MarkdownCode']))
            continue

        # Normal paragraph
        # Handle inline markdown (bold, italic, links)
        text = line.strip()
        # Convert **bold** to <b>bold</b>
        text = text.replace('**', '<b>', 1).replace('**', '</b>', 1)
        # Convert *italic* to <i>italic</i>
        text = text.replace('*', '<i>', 1).replace('*', '</i>', 1)

        if text:
            elements.append(Paragraph(text, styles['MarkdownText']))

        i += 1

    return elements

def convert_md_to_pdf(md_file_path, pdf_file_path):
    """Convert a markdown file to PDF"""
    # Read markdown file
    with open(md_file_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Create PDF document
    doc = SimpleDocTemplate(
        pdf_file_path,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    # Create styles
    styles = create_styles()

    # Parse markdown
    elements = parse_markdown_line_by_line(md_text, styles)

    # Build PDF
    doc.build(elements)
    print(f"✓ Converted {md_file_path} to {pdf_file_path}")

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python md_to_pdf.py <markdown_file> [output_pdf]")
        sys.exit(1)

    md_file = sys.argv[1]

    if not os.path.exists(md_file):
        print(f"Error: File {md_file} not found")
        sys.exit(1)

    # Determine output PDF path
    if len(sys.argv) >= 3:
        pdf_file = sys.argv[2]
    else:
        pdf_file = Path(md_file).stem + '.pdf'

    convert_md_to_pdf(md_file, pdf_file)

if __name__ == '__main__':
    main()