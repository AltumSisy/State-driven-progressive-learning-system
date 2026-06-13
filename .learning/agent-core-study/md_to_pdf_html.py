#!/usr/bin/env python3
"""
Markdown to PDF converter using markdown + xhtml2pdf
"""
import markdown
from xhtml2pdf import pisa
import sys
import os
from pathlib import Path

def convert_md_to_pdf_via_html(md_file_path, pdf_file_path):
    """Convert markdown to PDF via HTML intermediate"""

    # Read markdown file
    with open(md_file_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Convert markdown to HTML
    html_text = markdown.markdown(
        md_text,
        extensions=[
            'tables',
            'fenced_code',
            'codehilite',
            'toc',
            'nl2br'
        ]
    )

    # Create full HTML document with CSS styling
    html_document = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }
        h1 {
            font-size: 24pt;
            color: #000;
            text-align: center;
            margin-bottom: 20pt;
        }
        h2 {
            font-size: 18pt;
            color: #333;
            margin-top: 20pt;
            margin-bottom: 10pt;
        }
        h3 {
            font-size: 14pt;
            color: #444;
            margin-top: 15pt;
            margin-bottom: 8pt;
        }
        h4 {
            font-size: 12pt;
            color: #555;
            margin-top: 10pt;
            margin-bottom: 6pt;
        }
        p {
            margin: 6pt 0;
        }
        code {
            font-family: Courier New, monospace;
            font-size: 9pt;
            background-color: #f5f5f5;
            padding: 2pt 4pt;
            border-radius: 3pt;
        }
        pre {
            font-family: Courier New, monospace;
            font-size: 9pt;
            background-color: #f5f5f5;
            padding: 10pt;
            margin: 10pt 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        blockquote {
            margin: 10pt 0;
            padding: 10pt 20pt;
            background-color: #f9f9f9;
            border-left: 4pt solid #ccc;
            color: #666;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 10pt 0;
        }
        th, td {
            border: 1pt solid #ddd;
            padding: 8pt;
            text-align: left;
        }
        th {
            background-color: #f5f5f5;
            font-weight: bold;
        }
        hr {
            margin: 20pt 0;
            border: none;
            border-top: 1pt solid #ccc;
        }
        ul, ol {
            margin: 6pt 0;
            padding-left: 20pt;
        }
        li {
            margin: 3pt 0;
        }
        strong {
            font-weight: bold;
        }
        em {
            font-style: italic;
        }
    </style>
</head>
<body>
{html_text}
</body>
</html>
"""

    # Convert HTML to PDF
    with open(pdf_file_path, 'wb') as pdf_file:
        # Convert HTML string to PDF
        pisa_status = pisa.CreatePDF(
            html_document,
            dest=pdf_file,
            encoding='utf-8'
        )

    if pisa_status.err:
        print(f"❌ Error converting {md_file_path} to PDF")
        return False
    else:
        print(f"✓ Successfully converted {md_file_path} to {pdf_file_path}")
        return True

def main():
    """Main function to convert multiple markdown files"""
    if len(sys.argv) < 2:
        print("Usage: python md_to_pdf_html.py <markdown_file1> [markdown_file2] ...")
        sys.exit(1)

    success_count = 0
    for md_file in sys.argv[1:]:
        if not os.path.exists(md_file):
            print(f"Error: File {md_file} not found")
            continue

        # Determine output PDF path
        pdf_file = Path(md_file).stem + '.pdf'

        if convert_md_to_pdf_via_html(md_file, pdf_file):
            success_count += 1

    print(f"\n转换完成: {success_count}/{len(sys.argv[1:])} 个文件")

if __name__ == '__main__':
    main()