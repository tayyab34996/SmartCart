"""Build smartcart_report.docx from smartcart_report.md (Phase 12).

Usage (needs pandoc on the PATH):
    python docs/report/build_docx.py

Pandoc converts the Markdown with reference.docx (Calibri 11 pt, bordered tables), then
this script sets A4 pages with 2.2 cm margins and adds a footer with the page number.
The Markdown is the source; edit it, not the Word file.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

FOOTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p>'
    '<w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">SmartCart final report · prices are simulated · page </w:t></w:r>'
    '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
    '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'
    '</w:p></w:ftr>'
)
SECTION = (
    '<w:sectPr><w:footerReference w:type="default" r:id="rIdFtr1"/>'
    '<w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1304" w:right="1247" w:bottom="1304" w:left="1247" w:header="708" w:footer="567" w:gutter="0"/>'
    '</w:sectPr>'
)


def finish(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    files["word/footer1.xml"] = FOOTER.encode()
    rels = files["word/_rels/document.xml.rels"].decode()
    files["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>",
        '<Relationship Id="rIdFtr1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/footer" Target="footer1.xml"/></Relationships>').encode()
    types = files["[Content_Types].xml"].decode()
    files["[Content_Types].xml"] = types.replace(
        "</Types>",
        '<Override PartName="/word/footer1.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>').encode()
    doc = files["word/document.xml"].decode()
    files["word/document.xml"] = doc.replace("</w:body>", SECTION + "</w:body>").encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.docx"
        subprocess.run(["pandoc", "smartcart_report.md", "-o", str(raw), "--reference-doc=reference.docx",
                        "--resource-path=.", "-f", "markdown+pipe_tables"], cwd=HERE, check=True)
        finish(raw, HERE / "smartcart_report.docx")
    print("wrote docs/report/smartcart_report.docx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
