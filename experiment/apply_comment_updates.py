#!/usr/bin/env python3
"""
apply_comment_updates.py -- act on the five Word review comments.

Text edits:
  * Table 7: "375 MH/s (reported)" -> "375 MH/s (nominal)". The reviewer
    established that [4] does not confirm the 375 MH/s figure, so the cell must
    not attribute it to a report.
  * Table 3: "Manufacturer-rated device power" -> "Nameplate device power
    (vendor/preprint)". The 13 W basis is the vendor listing / preprint [35],
    not a manufacturer rating.
  * Section 1.3 novelty statement: state that the run is the same experiment
    as [35] and that its claims are superseded (comment 2 asked for this in
    Sections 1 and 2.5; 2.5 already has it).

Comment statuses:
  Each of the five comments is rewritten to the status verified against the
  current text. Two remain PARTLY FIXED on purpose: the RTX 3090 source and the
  public release/DOI are author actions, not text edits.

    python new/experiment/apply_comment_updates.py

Guarded: every anchor is asserted and the file is backed up before writing.
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import docx
from lxml import etree
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "new" / "ASIC-RAG-HEALTH_REVISED_final.docx"
BACKUP_DIR = ROOT / "new" / "backup"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

T7_OLD = "375 MH/s (reported)"
T7_NEW = "375 MH/s (nominal)"

T3_OLD = "Manufacturer-rated device power"
T3_NEW = "Nameplate device power (vendor/preprint)"

NOVELTY_OLD = "we therefore do not claim that the ASIC share provides security beyond a timestamp-style commitment."
NOVELTY_ADD = (
    " The 300 s LV06 run analysed here is the same experiment summarised in [35]; "
    "this paper supersedes that preprint's 100% verification-rate and 96% "
    "cost-reduction claims (Section 2.5, Table 6)."
)

COMMENTS = {
    0: (
        "CONFIRMED against the revised text: the hardware paragraph gives 500 GH/s "
        "and 13 W nameplate (vendor listings up to 15 W; companion preprint [35] "
        "gives 13 W). Dependent values were recomputed: 2.03 MH/W, 1.7x (RTX 3080) "
        "and 5.9x (RTX 3090), USD 19 over 5 years. The basis of the 13 W figure is "
        "now disclosed in 4.6, 8.1, the scope box, Table 2 and Data Availability; "
        "only a meter reading can supersede it. The ~500 GH/s figure remains "
        "manufacturer-rated and unverified."
    ),
    1: (
        "FIXED: 5.1 states that 26.34 MH/s is a share-derived rate limited by the "
        "bridge and firmware, not the chip hashrate; the gap versus 500 GH/s is "
        "about 19,000x, and a 500 GH/s device would return roughly 1,450 shares/s "
        "at D = 0.08. Table 3 defines the metric as shares x difficulty x 2^32 / "
        "duration. Device-reported hashrate, accepted/rejected counters and "
        "pool-difficulty logging were not captured in v1 and remain a v2 item."
    ),
    2: (
        "FIXED: (1) the prevhash rationale and the coinbase/witness prior art, "
        "including BIP-141 [44], are in 3.5; (2) the novelty statement and 2.5 "
        "state that the 300 s run is the same experiment reported in [35] and that "
        "[35]'s 100% verification and 96% cost-reduction claims are superseded by "
        "the reclassifications in Table 6; (3) the scope box in 1.4 and 4.8 state "
        "that D = 0.08 needs about 3.4e8 hashes (about 1 s on a GPU), so a share "
        "provides no unforgeability and is not an external timestamp unless the "
        "root is also anchored in a public chain, with OpenTimestamps [37] cited."
    ),
    3: (
        "PARTLY FIXED: attribution corrected to the single author (S. Mehammed), "
        "the RTX 3080 column is marked nominal, and the cell now reads "
        "'375 MH/s (nominal)' instead of 'reported', because [4] does not confirm "
        "that figure. The RTX 3090 '~120 MH/s' value is still marked 'assumed' "
        "with no source; it is retained only as order-of-magnitude context "
        "(Table 7 note) and should be cited or dropped before publication."
    ),
    4: (
        "PARTLY FIXED: Data Availability now carries an explicit author action "
        "for a tagged release, a Zenodo DOI and the SHA-256 of the archived JSON, "
        "and the revision package contains experiment/ (pow_verify.py, "
        "bridge_pow.py, run_v2.py) plus REPRODUCIBILITY.md section F. Still open: "
        "the public tagged release and DOI, pinned firmware/OS/Python versions, "
        "and archiving all 23 proofs plus the raw Stratum log (the JSON holds 10, "
        "which the paper discloses)."
    ),
}


def set_para_text(p: Paragraph, text: str) -> None:
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._element.getparent().remove(r._element)


def set_cell_text(cell, text: str) -> None:
    paras = cell.paragraphs
    for extra in paras[1:]:
        extra._element.getparent().remove(extra._element)
    set_para_text(paras[0], text)


def rewrite_comments_xml(data: bytes) -> bytes:
    root = etree.fromstring(data)
    seen = set()
    for c in root.findall(W + "comment"):
        cid = int(c.get(W + "id"))
        if cid not in COMMENTS:
            continue
        seen.add(cid)
        c.set(W + "date", "2026-11-14T00:00:00Z")
        paras = c.findall(W + "p")
        for extra in paras[1:]:
            c.remove(extra)
        first = paras[0]
        runs = first.findall(W + "r")
        keep = None
        for r in runs:
            if r.find(W + "annotationRef") is not None:
                keep = r
                break
        for r in runs:
            if r is not keep:
                first.remove(r)
        nr = etree.SubElement(first, W + "r")
        t = etree.SubElement(nr, W + "t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = COMMENTS[cid]
    missing = set(COMMENTS) - seen
    if missing:
        raise SystemExit(f"comment ids not found in comments.xml: {sorted(missing)}")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def patch_comments(doc_path: Path) -> None:
    tmp = doc_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(doc_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/comments.xml":
                data = rewrite_comments_xml(data)
            zout.writestr(item, data)
    tmp.replace(doc_path)


def main() -> int:
    if not DOC.exists():
        print(f"anchor not found: {DOC}")
        return 1
    doc = docx.Document(str(DOC))

    t7_cell = doc.tables[7].rows[1].cells[2]
    if t7_cell.text.strip() != T7_OLD:
        print(f"Table 7 cell changed: {t7_cell.text!r}")
        return 1

    t3_row = doc.tables[3].rows[7]
    if t3_row.cells[0].text.strip() != "Power" or t3_row.cells[1].text.strip() != T3_OLD:
        print(f"Table 3 power row changed: {[c.text for c in t3_row.cells]}")
        return 1

    novelty = next((p for p in doc.paragraphs if p.text.startswith("Novelty statement.")), None)
    if novelty is None or not novelty.text.rstrip().endswith(NOVELTY_OLD):
        print("novelty statement anchor not found or already edited")
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"ASIC-RAG-HEALTH_REVISED_final.{stamp}.docx"
    shutil.copy2(DOC, backup)
    print(f"backup: {backup.relative_to(ROOT)}")

    set_cell_text(t7_cell, T7_NEW)
    set_cell_text(t3_row.cells[1], T3_NEW)
    novelty.add_run(NOVELTY_ADD)

    doc.save(str(DOC))
    patch_comments(DOC)
    print(f"saved:  {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
