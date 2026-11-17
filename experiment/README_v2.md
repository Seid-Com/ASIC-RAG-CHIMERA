# Experiment v2: per-share proof-of-work verification

This directory is the instrument upgrade described in §4.8 and §8.2 of the
manuscript. It replaces the check the paper correctly refuses to call
verification:

```text
v1 (published):  block_hash = SHA256(merkle_root || ":" || nonce)
                 -> proves the bridge can reproduce its own string

v2 (this):       SHA256d(version || prevhash || merkle_root || ntime || nbits || nonce)
                     <= DIFF1_TARGET / share_difficulty
                 -> proves work was done on a header that carries the medical root
```

The v1 file is untouched and remains the record of the run that produced the
23 shares. v2 is a different instrument; it is not a re-analysis of v1 data.

## Files

| File | Role |
|---|---|
| `pow_verify.py` | Verification core: target math, 80-byte header assembly, share verdicts, standalone re-verifier, self-test |
| `bridge_pow.py` | Stratum bridge with a job registry, `job_id` attribution on submit, per-share verdicts, complete archive, raw traffic log |
| `run_v2.py` | Experiment runner. Reuses the record generator and `MerkleTree` from the archived v1 module read-only |
| `runs/` | Output directory created at run time |

## What changed, and why it matters

1. **Job registry.** v1 kept only `current_merkle_root`, so a share arriving
   after a job switch was stamped with the *new* root. v2 stores every
   `mining.notify` (prevhash, coinb1/coinb2, branches, version, nbits, ntime,
   extranonce1) keyed by `job_id`.
2. **Attribution.** `mining.submit` is parsed as
   `[worker, job_id, extranonce2, ntime, nonce]` and the share is bound to the
   job that produced it. Unknown `job_id` is recorded as a failure, not guessed.
3. **Real verification.** Each share's header is rebuilt from raw fields and its
   `SHA256d` compared to `DIFF1_TARGET / difficulty`. Both the difficulty target
   and the stricter `nbits` target are reported. v1 also advertised difficulty
   0.08 while sending `nbits = 0x1d00ffff` (difficulty 1); v2 validates against
   the difficulty actually pushed with `mining.set_difficulty`, and reports the
   `nbits` target separately rather than conflating them.
4. **Complete archive.** All shares, not `all_proofs[:10]`. `proofs.jsonl` is
   appended as each share lands, so a crash cannot truncate the record.
5. **Raw log.** `stratum_raw.jsonl` holds every message in both directions.
6. **Power provenance.** `--power-source {nameplate,meter}` is written into the
   results and decides the `efficiency_basis` string. The number itself is still
   derived; the label can no longer drift away from the basis.

## The prevhash byte-order problem

Stratum implementations disagree about the byte order of the prevhash field, and
the medical root is carried there. Rather than assume, verification tries three
layouts and records which one satisfies the target:

- `as_sent` — bytes exactly as transmitted (v1 behaviour)
- `word_swap` — reverse bytes within each 4-byte word
- `full_reverse` — reverse all 32 bytes

`prevhash_modes` in the results tells you which convention this firmware uses.
That measurement did not exist before; it is now an output.

## Running

Self-test first. It anchors header serialisation, hash byte order and target
comparison to the Bitcoin genesis block, then mines, verifies, tampers, and
checks all three byte orders. No hardware needed:

```bash
python pow_verify.py --self-test
```

End-to-end without hardware (built-in Stratum miner, easy target):

```bash
python run_v2.py --simulate --duration 15 --patients 12
```

Real run:

```bash
python run_v2.py --duration 300 --power 13.0 --power-source nameplate
# after fitting a meter:
python run_v2.py --duration 1800 --power <measured> --power-source meter
```

Independent re-verification of any results file (imports nothing from the
bridge, rebuilds headers from the stored raw fields):

```bash
python pow_verify.py runs/results_v2_<epoch>.json
```

Exit codes: `0` all shares verified, `2` at least one failed, `3` archive
cannot be verified (no job registry — this is what the v1 JSON returns).

## What a pass does and does not establish

**Establishes:** a share is a nonce whose header hashes below the target, and
that header contains the medical Merkle root in its prevhash field. This is the
record-to-work binding at the byte level that the manuscript lists as missing.
It also establishes which job the share belongs to.

**Does not establish:** that the ASIC, rather than the host CPU, produced the
nonce. At difficulty 0.08 a share costs about 0.34 GH, which a desktop can do in
roughly a second. Attribution still rests on the rate/power cross-check:
measured hashrate consistent with the device rating, and metered power that
matches a device that is actually hashing. Stratum carries no "ASIC-reported
hash" field, so the verifier cannot read one; the checksum is the physics, not
the protocol.

**Does not establish:** that the firmware assembled the header the way
`pow_verify.py` does. That is exactly what `prevhash_modes` measures. If no
layout matches and shares keep arriving, the firmware is doing something else
(rolled ntime, different coinbase assembly, extra nonce handling) and the raw
log in `stratum_raw.jsonl` is what a diagnosis needs.

## Reporting v2 results in the manuscript

- §4.8: replace "we checked whether the stored `b` satisfies T. It does not"
  with the v2 verdict counts. `23/23` (or `N/N`) becomes *PoW verified*, and the
  old bridge-commitment check is reported separately as *consistency*.
- §4.8 and §8.2: the minimum-change list (store `job_id`, header, target, check
  `SHA256d < T`) is now implemented; the section should describe it in the
  present tense and cite this directory.
- §8.1: the "only first ten proof records are archived" limitation disappears
  for v2 runs.
- Table 4: add `PoW verified` and `prevhash mode` rows.
- Abstract: "does not independently verify the ASIC's header hash against the
  difficulty target" applies to the v1 run only; a v2 run must be described
  separately, not merged with the 23-share dataset.

## Power provenance in the v1 archive (resolved)

`archive/.../NEW/definitive_results_1766347344.json` records `power_watts: 9.0`
and derives `efficiency_mhw: 2.93` from it; `Config.LV06_POWER_WATTS` is also
9.0. That constant is stale. The manuscript uses 13 W (2.03 MH/W), the value
documented in §4.2 from vendor listings (up to 15 W) and the companion preprint.
Both are nameplate assumptions; neither is metered.

13 W is the better-sourced value and is 44% above the stale constant, so it
lowers reported efficiency and raises reported energy cost; it cannot overstate
the device's advantage. The difference is now disclosed in §4.6, §8.1 and Data
Availability, and the release carries `POWER_PROVENANCE.md` mapping every derived
quantity to the value it uses. When a meter reading exists, supersede both and
record `power_source: meter`.
