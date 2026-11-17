# Reproducibility kit: LV06 Stratum-anchoring experiment

## A. Before the run (record all of these)
- [ ] Device label photo: model, rated hashrate, rated power
- [ ] Firmware name + version (device web UI -> About/System)
- [ ] Pool-difficulty / "suggest difficulty" settings on device and in the bridge
- [ ] Host OS, Python version (`python3 -V`), bridge commit hash
- [ ] Power meter or smart plug connected (log watts every 10 s)

## B. Runs
1. Repeat the 300 s run (x3) for variance.
2. Run 30-60 min once.
3. Control run: send an all-zero prevhash job only, to compare the share rate.
Save for each run: raw Stratum log (every notify/submit/response), device-reported hashrate and
accepted/rejected counters (screenshot or API dump), meter CSV, ALL shares (not only the first 10).

## C. Questions the logs must answer
- Why 23 shares instead of ~1,450/s at the rated hashrate? (firmware difficulty floor? bridge rate limit?
  rejected-share counter? job-switch frequency?)
- Does the device-reported hashrate match the share-derived rate?
- Does each share's SHA-256d(header) fall below target? (needs the full header per share and job_id parsing)

## D. Release
- [ ] Tag a release containing: stratum bridge, run script, results JSON, analysis scripts, `recompute_derived.py`
- [ ] Archive on Zenodo, copy DOI into the paper's Data Availability note
- [ ] `sha256sum definitive_results_*.json` and paste the hash into the paper
- [ ] README: state clearly which parts are real hardware vs software simulation


## E. After
Edit INPUTS in `recompute_derived.py` (metered power, measured hashrate), re-run it, and update the
abstract, Tables 4/6/7/9 and Section 5.1 with the printed values.

## F. Instrument v2 (per-share PoW verification)
`experiment/` replaces the bridge's self-check with a real header/target check.

- [ ] `python experiment/pow_verify.py --self-test` passes (genesis vector + tamper tests)
- [ ] `python experiment/run_v2.py --simulate --duration 15` passes end-to-end (no hardware)
- [ ] Real run: `python experiment/run_v2.py --power <W> --power-source meter`
- [ ] Re-verify independently: `python experiment/pow_verify.py experiment/runs/results_v2_*.json`
- [ ] Record `prevhash_modes` from the results; it identifies the firmware's prevhash byte order
- [ ] Add `PoW verified` and `prevhash mode` rows to Table 4; rewrite Section 4.8 in the present tense
- [ ] Keep the v1 23-share dataset separate from any v2 run; they are different instruments

Details and caveats: `experiment/README_v2.md`.
