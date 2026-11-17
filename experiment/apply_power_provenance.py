#!/usr/bin/env python3
"""
apply_power_provenance.py -- disclose the 13 W vs 9.0 W mismatch in place.

The instrument and the released JSON use 9.0 W; the manuscript reports 13 W.
Neither is metered. This stage keeps 13 W (the more conservative assumption)
and states the 9.0 W provenance wherever the paper and the archive meet.

    python new/experiment/apply_power_provenance.py

Guarded: every anchor is asserted, and the file is backed up before writing.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import docx
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "new" / "ASIC-RAG-HEALTH_REVISED_final.docx"
BACKUP_DIR = ROOT / "new" / "backup"


def set_para_text(p: Paragraph, text: str) -> None:
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._element.getparent().remove(r._element)


def find_para(doc, needle: str) -> Paragraph:
    hits = [p for p in doc.paragraphs if needle in p.text]
    if len(hits) != 1:
        raise SystemExit(f"anchor not unique ({len(hits)} hits): {needle!r}")
    return hits[0]


def set_cell_text(cell, text: str) -> None:
    paras = cell.paragraphs
    for extra in paras[1:]:
        extra._element.getparent().remove(extra._element)
    set_para_text(paras[0], text)


P116_OLD = "The 13 W figure is the manufacturer rating, not a meter reading."
P116_NEW = (
    "The power figure is a nameplate assumption, not a meter reading. Section 4.2 "
    "records its basis: vendor listings quote up to 15 W and the companion "
    "preprint gives 13 W, the value used here. The instrument's configuration "
    "retained an older 9.0 W constant, so the released archive derives 2.93 MH/W "
    "from 9.0 W whereas this paper reports 2.03 MH/W from 13 W. The higher value "
    "is the conservative choice: it lowers reported efficiency and the "
    "relative-efficiency multiples and raises reported energy cost. Neither value "
    "is metered. The released archive carries a provenance note that maps each "
    "derived quantity to the value it uses."
)

P192_OLD = "Power is nameplate, not metered; efficiency is derived."
P192_NEW = (
    "Power is nameplate, not metered; efficiency is derived. The instrument "
    "configuration and archived JSON use an older 9.0 W constant (2.93 MH/W), "
    "whereas this paper reports 13 W (2.03 MH/W), the value documented in "
    "Section 4.2; neither is metered."
)

P222_OLD = (
    "The archived JSON contains the first ten proof records; the summary counters "
    "cover all 23 accepted shares, as explained in Section 4.7."
)
P222_NEW = P222_OLD + (
    " The JSON's power_watts field is the instrument's older 9.0 W constant, not "
    "the 13 W nameplate used in this paper; a provenance note in the release "
    "explains the difference."
)

T0_OLD = "The 13 W figure is the manufacturer rating."
T0_NEW = (
    "The 13 W figure is a nameplate value (vendor listings quote up to 15 W), not "
    "a measurement."
)

T2R8_OLD = "13 W is the manufacturer rating"
T2R8_NEW = "13 W is nameplate (vendor listings up to 15 W), not metered"


def main() -> int:
    doc = docx.Document(str(DOC))

    p116 = find_para(doc, P116_OLD)
    p192 = find_para(doc, P192_OLD)
    p222 = find_para(doc, P222_OLD)

    if "23/23 figure is a bridge-side consistency check" not in p116.text:
        raise SystemExit("P116 is not the expected results paragraph")
    if "Power is nameplate, not metered; efficiency is derived." not in p192.text:
        raise SystemExit("P192 is not the expected limitation bullet")
    if "definitive_results_1766347344.json" not in p222.text:
        raise SystemExit("P222 is not the Data Availability paragraph")

    scope_cell = doc.tables[0].rows[0].cells[0]
    scope_para = next((q for q in scope_cell.paragraphs if T0_OLD in q.text), None)
    if scope_para is None:
        raise SystemExit("scope box bullet with the 13 W sentence not found")
    r8 = doc.tables[2].rows[8]
    if r8.cells[0].text.strip() != "Power measurement":
        raise SystemExit(f"T2 R8 is not the power row: {r8.cells[0].text!r}")
    if T2R8_OLD not in r8.cells[2].text:
        raise SystemExit(f"T2 R8 evidence changed unexpectedly: {r8.cells[2].text!r}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"ASIC-RAG-HEALTH_REVISED_final.{stamp}.docx"
    shutil.copy2(DOC, backup)
    print(f"backup: {backup.relative_to(ROOT)}")

    set_para_text(p116, p116.text.replace(P116_OLD, P116_NEW))
    set_para_text(p192, p192.text.replace(P192_OLD, P192_NEW))
    set_para_text(p222, p222.text.replace(P222_OLD, P222_NEW))
    set_para_text(scope_para, scope_para.text.replace(T0_OLD, T0_NEW))
    set_cell_text(r8.cells[2], T2R8_NEW)

    doc.save(str(DOC))
    print(f"saved:  {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
