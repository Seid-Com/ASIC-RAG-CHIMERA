# Manuscript edit log — v2 verification edits

**File:** `new/ASIC-RAG-HEALTH_REVISED_final.docx`
**Applied:** 2026-11-14
**Backup:** `new/backup/ASIC-RAG-HEALTH_REVISED_final.20261114-163759.docx`
**SHA-256 before:** `4C14995FE0846EB9FA802ED75EA6F2A1766E80242F72E4A0EC8FDCE088162BDA`
**SHA-256 after:** `77589E6C146683A9DA047737E4B4F833684A0A21B717CAEEFCE1B7430BA590EE`
**Driver:** `new/experiment/apply_doc_edits_v2.py` (asserts every anchor before writing)

The edit is limited to four paragraph ranges and one table row. No number in the
manuscript was changed. A v2 instrument now exists, but **no v2 hardware run has
been performed**, so nothing added here reports a v2 result.

## Applied edits

| # | Location | Change |
|---|---|---|
| 1 | §4.8, P131 | Appended the `D = 0.08` vs `nbits = 0x1d00ffff` reconciliation: the two imply targets differing by 12.5×, the archive cannot show which one the device filtered against, and if it filtered against `nbits` the effective hashrate in Table 4 would be 12.5× higher. |
| 2 | §4.8, P133 | Replaced "the ASIC-reported header hash" with "its reconstructed SHA-256d digest". Stratum v1 has no field in which the device reports a header hash, so the old wording specified something unimplementable. |
| 3 | §4.8, new P134 (after P133) | New paragraph describing the implemented v2 instrument: immutable job registry, `job_id` parsing, header reconstruction, dual-target check, three prevhash byte-order variants, and the residual attribution limit (rate/power cross-check, not protocol). |
| 4 | Table 2, row 7 | Status `Not implemented` → `Implemented in v2, not used in this run`; evidence now names the v2 header/target check. |
| 5 | §8.1, P194 | Appended: v2 writes every share to `proofs.jsonl` and every Stratum message to `stratum_raw.jsonl`, so the ten-record truncation cannot recur in a v2 run; the limitation still applies to the 23-share dataset. |
| 6 | §8.2, item 1 (P203) | Rewrote the future-work item: immutable job registry, raw `mining.notify`/`mining.submit` retention, reconstructed header and digest, both targets, recorded byte order. Dropped the non-existent "ASIC-reported header hash". |

Edit 2 is a consistency follow-on to edit 6: P133 promised to store an
ASIC-reported hash, and §8.2 asked for the same field. Neither is obtainable
from Stratum v1, so both now describe reconstruction instead.

## Applied text (verbatim additions)

**P131, appended:**

> The two settings are not equivalent: nbits = 0x1d00ffff is the compact
> encoding of the Bitcoin difficulty-1 target T₁, whereas D = 0.08 corresponds
> to T = 12.5 T₁. The nbits field in the header therefore advertises a target
> 12.5 times smaller, and hence 12.5 times harder, than the share target the
> bridge pushed with mining.set_difficulty. The archive cannot show which of the
> two the device filtered against, because it stores neither the header nor the
> raw notify message. This ambiguity is a further reason to record the header at
> submission time; the v2 verifier described below records both targets and
> reports them separately rather than assuming they coincide. If the device
> filtered against nbits rather than against the pushed difficulty, the expected
> work per share is 12.5 times larger and the effective hashrate in Table 4 would
> be 12.5 times higher; the target actually applied must therefore be recorded
> before either value can be treated as measured.

**New P134:**

> A v2 instrument implementing this check accompanies the reproducibility
> materials (experiment/pow_verify.py and experiment/bridge_pow.py). It stores
> every mining.notify as an immutable job record (job_id, prevhash as
> transmitted, coinb1, coinb2, Merkle branches, version, nbits, ntime,
> extranonce1), parses job_id from each mining.submit, rebuilds the 80-byte
> header, and tests SHA-256d(header) against both the pushed share difficulty and
> the nbits target. Stratum v1 has no field in which the device reports its
> header hash, so the verifier reconstructs the header instead of reading one.
> Because the firmware's prevhash byte order is not documented, the verifier
> tries three layouts — as transmitted, word-swapped within 4-byte words, and
> fully reversed — and records which one, if any, satisfies the target; the
> result is a measurement of the convention rather than an assumption about it.
> A passing share establishes that a header carrying the Merkle root in its
> prevhash field hashes below the target. It does not establish that the ASIC
> produced the nonce rather than the host: at D = 0.08 a share costs about
> 3.4 × 10⁸ hashes, roughly one second on a desktop GPU, so device attribution
> still rests on the rate and power cross-check. The v2 instrument is a separate
> run, and its results are not merged with the 23-share dataset reported here.

**P194, appended:**

> The v2 instrument described in Section 4.8 writes every share to an
> append-only proofs.jsonl and every Stratum message to stratum_raw.jsonl, so
> this truncation cannot recur in a v2 run; the limitation continues to apply to
> the 23-share dataset analyzed here.

## Status of the 17-item revision list

The pasted list targets an earlier manuscript: it cites §3.3, §3.4, Table 2,
§5.4 and §6, and quotes text that does not occur in this file (the file has
§4.8, §4.9, §8.1, §8.2, §9, and Tables 1–10). Items are mapped by content.

| # | Spec item | Status |
|---|---|---|
| 1 | §3.3 final para: preserve job params, resolve `job_id`, rebuild header, SHA-256d, compare target | **Applied** — P133 amended and P134 added |
| 2 | §3.4 stage 5 "Commitment assessment" disclaimer | **Already present, stronger** — P128 states the check is consistency only and does not show the ASIC did the work. Quoted string absent. |
| 3 | Table 2 "Independent PoW verification" definition | **Applied** — T2 R7 now carries status and the reconstruction/target definition |
| 4 | §3.4 attribution paragraph | **Already present, stronger** — P132 covers current-root attribution, unparsed `job_id`, missing word-swap, uncaptured header, "plausible but not proven". |
| 5 | §4 zero-root paragraph → "potentially record-associated" | **Already present in substance** — zero-root placeholder is discussed (P117, T5 R5) and record-bound shares are labelled an upper bound (T5 R6). Quoted text absent. |
| 6 | §4 "Two verification defects" | **Already present** — P131–P133 describe both defects (no PoW check; wrong-root attribution). Quoted paragraph absent. |
| 7 | §3.4 archive requirement after five stages | **Already present** — P128 and P194 state only ten proofs are archived; T5 R7 explains `all_proofs[:10]`. No anchor for the quoted sentence. |
| 8 | §4 archive paragraph: require raw messages, headers, nonces, timestamps, outcomes | **Applied** — P194 now names `proofs.jsonl`/`stratum_raw.jsonl`; full requirement in P203 |
| 9 | Table 4 "Archived proof records" row → mark legacy | **No change** — T4 R6 is a results row (`10 (1 zero-root, 9 non-zero)`), and T5 R7 already explains the truncation. Rewriting a result row to state a requirement would mix claim and evidence. |
| 10 | §6 future-work item 3: expand archive list | **Applied** — P203 (§8.2 item 1) rewritten |
| 11 | Table 2 power/efficiency rows → require external metering | **Already present** — T3 R7/R8, T4 R14/R15, T7 R2/R3/R7 and the scope box all label power nameplate and efficiency derived. The spec's two-column layout does not match this file. |
| 12 | §4 power paragraph: voltage, current, power factor, interval, uncertainty | **Not applied** — see "Deliberately not applied" below |
| 13 | §5.4 sixth limitation | **Already present** — P192 (§8.1) states power is nameplate, not metered, and efficiency derived |
| 14 | Abstract final sentence: remove implied verified anchoring | **Already present** — abstract/scope box already limit the claim to bridge-side consistency; quoted sentence absent |
| 15 | §1.3 contribution 3: make verification gap explicit | **Already present** — verification gap is stated in P128–P133, §4.9 and §8.1; the §1.3 text differs from the quote |
| 16 | §5.1 final sentence: "every" → "any" accepted share | **Already present, stronger** — P190–P191 and P213 say the record-to-root binding is plausible but not proven at the byte level; quoted sentence absent |
| 17 | §6 final paragraph: align conclusion | **Already present** — P213 limits the result to the pipeline and bridge-record consistency, not independent PoW, blockchain, RAG, or deployment |

## Deliberately not applied

**"9 W" power substitutions (spec items 11–13).** The manuscript contains no
"9 W" figure; every power reference is 13 W and every derived value is
consistent with 13 W (26.34 MH/s, 2.03 MH/W, 1.08 Wh, 3.80 USD/yr, 59 USD TCO).
The 9 W value exists only in the released archive
(`power_watts: 9.0`, `efficiency_mhw: 2.93`) and in
`Config.LV06_POWER_WATTS = 9.0`. Substituting 9 W into the manuscript would
break its internal arithmetic; substituting 13 W into the archive would rewrite
a published dataset. Neither was done. The mismatch is disclosed instead, not
silently reconciled: see "Stage 2" below and
`archive/REAL_DATA_LV06/chimera_handoff/NEW/POWER_PROVENANCE.md`.

**Power-metering method text (spec item 12).** Deferred with the power
substitution. Adding "report voltage, current, power factor, interval and
uncertainty" is text-only and does not require data, but it belongs with the
metering revision; it can be added without touching any number.

**v2 results.** No v2 hardware run exists, so no `PoW verified N/N` count,
`prevhash_modes` distribution, or changed Table 4 result was written. The
instrument is described in the future/available tense, and T2 R7 says explicitly
"not used in this run".

## Verification performed

- `zipfile.ZipFile(...).testzip()` returns `None` (no corrupt members).
- Paragraph count 275 → 276 (one insertion); table count unchanged at 11.
- `difflib` over all paragraph text shows changes only at P131, P133 + inserted
  P134, P194 and P203. `difflib` over table cells shows changes only in T2 R7.
- The inserted paragraph has the same style (`Normal`) and identical `pPr` XML
  as P133, so spacing and indentation match.
- Every anchor string was asserted before writing; the script exits without
  saving if any is missing.

## Still open

1. ~~Decide the 13 W vs 9 W provenance question.~~ **Done:** 13 W retained as the
   conservative assumption, 9.0 W disclosed (Stage 2).
2. Run v2 on the device, then add the real verdict counts and byte-order result.
3. Optional text-only edit: metering method sentence in §8.1 and §8.2 item 2.

---

# Stage 2 — power provenance (applied 2026-11-14)

**Driver:** `new/experiment/apply_power_provenance.py`
**Backup (stage-1 state):** `new/backup/ASIC-RAG-HEALTH_REVISED_final.20261114-164348.docx`
**Backup (pristine original):** `new/backup/ASIC-RAG-HEALTH_REVISED_final.20261114-163759.docx`
**SHA-256 after Stage 2:** `62DCB2D974829CF3AF2F2911E63BA15416A29DCFB6408EB669A57A59599B3ABD`

## The decision

P116 called 13 W "the manufacturer rating". That sentence was wrong in a
specific way: §4.2 already documents 13 W from vendor listings (which quote up
to 15 W) and the companion preprint, while the instrument's `Config` retained an
older 9.0 W constant that the released JSON inherited. So the paper's number is
the better-sourced one; the disclosure problem is on the archive side.

| Option | Consequence |
|---|---|
| Revert the paper to 9.0 W | Matches the archive, but changes ~10 numbers and adopts the stale, less conservative constant; still unmetered |
| Replace 9.0 W in the archive with 13 W | Rewrites a published dataset; rejected |
| **Keep 13 W, disclose the stale 9.0 W** | No number changes; the paper keeps the value documented in §4.2; the archive stays intact and its derived values are explained |

The third option was applied. 13 W is 44% above the stale 9.0 W constant, so it
lowers reported efficiency (2.03 vs 2.93 MH/W), lowers the multiples against the
GPUs, and raises reported energy and TCO (USD 59 vs 53). It cannot flatter the
device.

## Edits

| Location | Change |
|---|---|
| §4.6 P116 | Replaced "13 W is the manufacturer rating" with the provenance: 13 W is the §4.2 vendor/preprint figure, the instrument retained a stale 9.0 W constant that the archive inherited, neither is metered |
| §8.1 P193 | Extended the power limitation bullet with both values and their efficiencies |
| Scope box (Table 0) | "The 13 W figure is the manufacturer rating" → "nameplate value (vendor listings quote up to 15 W), not a measurement" |
| Table 2 row 8 | "13 W is the manufacturer rating" → "13 W is nameplate (vendor listings up to 15 W), not metered" |
| Data Availability P222 | Added that the JSON's `power_watts` is the instrument's older 9.0 W constant, not the paper's 13 W, and points to the release note |

No table, number, or derived value was changed.

## Files added or updated

| File | Change |
|---|---|
| `archive/REAL_DATA_LV06/chimera_handoff/NEW/POWER_PROVENANCE.md` | New. Explains that 9.0 W is a stale instrument constant and 13 W is the §4.2 vendor/preprint figure; maps every derived quantity to both; states what supersedes it. The JSON itself is untouched. |
| `new/experiment/README_v2.md` | "Known provenance issue" replaced with the resolved provenance section and a pointer to the release note |
| `new/recompute_derived.py` | Prints both efficiencies (2.03 at 13 W, 2.93 at 9.0 W); all other output unchanged |
| `new/EDIT_LOG_v2.md` | This section |

## Verification

- `difflib` against the pristine backup shows only P116, P131, P133 + inserted
  P134, P194, P203 and P223 changed — the union of Stage 1 and Stage 2.
- `difflib` over table cells shows only the scope-box power bullet (Table 0) and
  Table 2 rows 7–8 (Stage 1 + Stage 2).
- `zipfile.testzip()` returns `None`; the document opens with 276 paragraphs and
  11 tables.
- `recompute_derived.py` output still reproduces 26.34 MH/s, 2.03 MH/W,
  1.08 Wh, 18,983×, USD 3.80/yr, USD 19/5 yr, USD 59 TCO.

## Residual limitation

Both numbers remain assumptions. Until a meter reading exists, no power-derived
value in the paper or the archive is a measurement, and the release now says so
in three places. The metering-method sentence (voltage, current, power factor,
interval, uncertainty) is still deferred to the metering revision.

---

# Stage 3 — Word review comments (applied 2026-11-14)

**Driver:** `new/experiment/apply_comment_updates.py`
**Backup:** `new/backup/ASIC-RAG-HEALTH_REVISED_final.20261114-170007.docx`
**SHA-256 after Stage 3:** `7B848D2E228EEAF6CA07DE28A9EEA7EDE96DFCEA74F1D33B32E65DAEFE6A4D05`

The manuscript carries five Word comments authored "Claude (review)". Each was
checked against the text rather than trusting its status prefix.

| # | Anchor | Status before | Verified state | Action |
|---|---|---|---|---|
| 0 | §4.2 hardware | FIXED (please confirm) | 500 GH/s, 13 W nameplate, 2.03 MH/W, 1.7×/5.9×, USD 19 all consistent | Confirmed in the comment; Table 3 power label corrected |
| 1 | §5.1 | FIXED | 19,000×, share-derived, ~1,450 shares/s stated | No text change; device counters remain a v2 item |
| 2 | §3.5 novelty | PARTLY FIXED | BIP-141 [44] in 3.5; same-dataset/supersession in 2.5; 3.4×10⁸ hashes and OpenTimestamps in 1.4/4.8 | Added the same-dataset sentence to §1.3; status → FIXED |
| 3 | Table 7 | FIXED | 375 MH/s was still labelled "reported"; RTX 3090 still "assumed" with no source | "reported" → "nominal"; status → PARTLY FIXED |
| 4 | Data Availability | PARTLY FIXED | Placeholder for tag/DOI/SHA-256 present; 10 of 23 proofs archived | No text change (author actions); status kept PARTLY FIXED |

## Text edits

| Location | Change |
|---|---|
| Table 7, RTX 3080 hashrate cell | `375 MH/s (reported)` → `375 MH/s (nominal)` — [4] does not confirm that figure |
| Table 3, power row | `Manufacturer-rated device power` → `Nameplate device power (vendor/preprint)` — the 13 W basis is the vendor listing and [35] |
| §1.3 novelty statement (P30) | Appended that the run is the same experiment as [35] and that [35]'s 100% verification and 96% cost-reduction claims are superseded (comment 2 asked for §1 and §2.5) |

All five comment bodies were rewritten to the verified status and re-dated
2026-11-14. `word/comments.xml` was patched in place; comment anchors, authors
and IDs are unchanged.

## Verification

- `difflib` against the pristine original shows P30 plus the Stage 1/2 ranges,
  and only four changed table cells beyond Stage 2 (T3 power label and T7
  hashrate cell).
- `zipfile.testzip()` returns `None`; 276 paragraphs, 11 tables, 5 comments.
- `manufacturer rating` count is 0; "reported" no longer appears in the RTX 3080
  hashrate cell.

## Still open (author actions, not text)

1. RTX 3090 `~120 MH/s` has no source: cite or drop the column.
2. Tagged release, Zenodo DOI, SHA-256 of the JSON.
3. Firmware / OS / Python versions and pool-difficulty configuration.
4. Archive all 23 proofs and the raw Stratum log, not only the first 10.

## Known mismatch outside this file

`revision/RESPONSE_TO_REVIEWERS.docx` still uses 9 W (5×), 2.93 MH/W (2×),
7,600× (1×) and 200 GH/s (2×), and its P89 calls the 9 W/13 W discrepancy
"unresolved". It must be updated to 13 W / 2.03 MH/W / ~19,000× or it will
contradict the manuscript.

