#!/usr/bin/env python3
"""
apply_doc_edits_v2.py -- apply the agreed v2 manuscript edits in place.

Guarded: every anchor string is asserted before anything is written, and the
original is copied to new/backup/ first. Run from the repo root:

    python new/experiment/apply_doc_edits_v2.py

Edits
  1. P131  append the D=0.08 vs nbits=0x1d00ffff target reconciliation
  2. P133  replace "ASIC-reported header hash" with the reconstructed header
  3. after P133  new paragraph describing the implemented v2 instrument
  4. T2 R7  status/evidence -> implemented in v2, not used in this run
  5. P193  append the v2 all-shares archive note
  6. P202  drop the non-existent ASIC-reported hash; require raw records
"""

from __future__ import annotations

import shutil
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import docx
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "new" / "ASIC-RAG-HEALTH_REVISED_final.docx"
BACKUP_DIR = ROOT / "new" / "backup"


def set_para_text(p: Paragraph, text: str) -> None:
    """Replace a paragraph's text, keeping the first run's formatting."""
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._element.getparent().remove(r._element)


def append_text(p: Paragraph, text: str) -> None:
    runs = p.runs
    if runs:
        runs[-1].text = runs[-1].text + text
    else:
        p.add_run(text)


def set_cell_text(cell, text: str) -> None:
    paras = cell.paragraphs
    for extra in paras[1:]:
        extra._element.getparent().remove(extra._element)
    set_para_text(paras[0], text)


def insert_paragraph_after(p: Paragraph, text: str) -> Paragraph:
    new_el = deepcopy(p._element)
    p._element.addnext(new_el)
    new_p = Paragraph(new_el, p._parent)
    set_para_text(new_p, text)
    return new_p


def find_para(doc, needle: str) -> Paragraph:
    hits = [p for p in doc.paragraphs if needle in p.text]
    if len(hits) != 1:
        raise SystemExit(f"anchor not unique ({len(hits)} hits): {needle!r}")
    return hits[0]


# ---------------------------------------------------------------------------
# New text
# ---------------------------------------------------------------------------

P131_ADD = (
    " The two settings are not equivalent: nbits = 0x1d00ffff is the compact "
    "encoding of the Bitcoin difficulty-1 target T₁, whereas D = 0.08 "
    "corresponds to T = 12.5 T₁. The nbits field in the header therefore "
    "advertises a target 12.5 times smaller, and hence 12.5 times harder, than "
    "the share target the bridge pushed with mining.set_difficulty. The archive "
    "cannot show which of the two the device filtered against, because it stores "
    "neither the header nor the raw notify message. This ambiguity is a further "
    "reason to record the header at submission time; the v2 verifier described "
    "below records both targets and reports them separately rather than assuming "
    "they coincide. If the device filtered against nbits rather than against the "
    "pushed difficulty, the expected work per share is 12.5 times larger and the "
    "effective hashrate in Table 4 would be 12.5 times higher; the target actually "
    "applied must therefore be recorded before either value can be treated as "
    "measured."
)

P133_OLD = "the ASIC-reported header hash"
P133_NEW = "its reconstructed SHA-256d digest"

P133_INSERT = (
    "A v2 instrument implementing this check accompanies the reproducibility "
    "materials (experiment/pow_verify.py and experiment/bridge_pow.py). It stores "
    "every mining.notify as an immutable job record (job_id, prevhash as "
    "transmitted, coinb1, coinb2, Merkle branches, version, nbits, ntime, "
    "extranonce1), parses job_id from each mining.submit, rebuilds the 80-byte "
    "header, and tests SHA-256d(header) against both the pushed share difficulty "
    "and the nbits target. Stratum v1 has no field in which the device reports "
    "its header hash, so the verifier reconstructs the header instead of reading "
    "one. Because the firmware's prevhash byte order is not documented, the "
    "verifier tries three layouts — as transmitted, word-swapped within 4-byte "
    "words, and fully reversed — and records which one, if any, satisfies the "
    "target; the result is a measurement of the convention rather than an "
    "assumption about it. A passing share establishes that a header carrying the "
    "Merkle root in its prevhash field hashes below the target. It does not "
    "establish that the ASIC produced the nonce rather than the host: at "
    "D = 0.08 a share costs about 3.4 × 10⁸ hashes, roughly one second on a "
    "desktop GPU, so device attribution still rests on the rate and power "
    "cross-check. The v2 instrument is a separate run, and its results are not "
    "merged with the 23-share dataset reported here."
)

T2_STATUS = "Implemented in v2, not used in this run"
T2_EVIDENCE = (
    "Reported run: bridge commitment only; v2 (experiment/) reconstructs the "
    "80-byte header and checks SHA-256d < target"
)

P193_ADD = (
    " The v2 instrument described in Section 4.8 writes every share to an "
    "append-only proofs.jsonl and every Stratum message to stratum_raw.jsonl, so "
    "this truncation cannot recur in a v2 run; the limitation continues to apply "
    "to the 23-share dataset analyzed here."
)

P202_NEW = (
    "Independent PoW verification: parse job_id from each submit, resolve it "
    "against an immutable job registry, and store the raw mining.notify and "
    "mining.submit messages together with the reconstructed 80-byte header, its "
    "SHA-256d digest, and both targets (the pushed share difficulty and nbits). "
    "Stratum v1 carries no ASIC-reported header hash, so the header must be "
    "reconstructed and the reconstruction validated against the recorded job "
    "fields. Check SHA-256d(header) < T and that the header's prevhash field "
    "equals the job's Merkle root after the correct byte order is applied; record "
    "which byte order satisfied the target. Report the fraction of shares that "
    "pass."
)


def main() -> int:
    doc = docx.Document(str(DOC))

    p131 = find_para(doc, "The expected number of hashes per share is D × 2³²")
    p133 = find_para(doc, "A correct verifier would store, for each share")
    p193 = find_para(doc, "The archived JSON contains only the first ten proof records")
    p202 = find_para(doc, "Independent PoW verification: parse job_id from each submit")

    # --- assertions before writing anything -------------------------------
    for p, needle in [
        (p131, "it did not reconstruct the header or check the target"),
        (p131, "We report it explicitly to prevent the 23/23 result"),
        (p133, P133_OLD),
        (p133, "It is specified in Section 8.2."),
        (p193, "Full telemetry is not preserved in the archive."),
        (p202, "the ASIC-reported header hash"),
        (p202, "Report the fraction of shares that pass."),
    ]:
        if needle not in p.text:
            raise SystemExit(f"expected text missing from P: {needle!r}")

    table = doc.tables[2]
    row = table.rows[7]
    if row.cells[0].text.strip() != "Independent PoW verification":
        raise SystemExit(f"T2 R7 is not the expected row: {row.cells[0].text!r}")
    if "Not implemented" not in row.cells[1].text:
        raise SystemExit(f"T2 R7 status changed unexpectedly: {row.cells[1].text!r}")

    # --- backup -----------------------------------------------------------
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"ASIC-RAG-HEALTH_REVISED_final.{stamp}.docx"
    shutil.copy2(DOC, backup)
    print(f"backup: {backup.relative_to(ROOT)}")

    # --- edit 1: P131 -----------------------------------------------------
    append_text(p131, P131_ADD)

    # --- edits 2+3: P133 and the new paragraph after it -------------------
    set_para_text(p133, p133.text.replace(P133_OLD, P133_NEW))
    insert_paragraph_after(p133, P133_INSERT)

    # --- edit 4: Table 2, row 7 ------------------------------------------
    set_cell_text(row.cells[1], T2_STATUS)
    set_cell_text(row.cells[2], T2_EVIDENCE)

    # --- edit 5: P193 -----------------------------------------------------
    append_text(p193, P193_ADD)

    # --- edit 6: P202 -----------------------------------------------------
    set_para_text(p202, P202_NEW)

    doc.save(str(DOC))
    print(f"saved:  {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
