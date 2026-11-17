#!/usr/bin/env python3
"""Recompute every derived number in the manuscript from raw inputs.
Edit the INPUTS block (use metered power when you have it), then run:
    python3 recompute_derived.py
"""
# ---- INPUTS (measured or assumed; edit these) ----
SHARES        = 23        # accepted shares in the run
DURATION_S    = 300.04    # run length, seconds
SHARE_DIFF    = 0.08      # configured share difficulty
POWER_W       = 13.0      # manuscript assumption; higher = conservative (see POWER_PROVENANCE.md)
POWER_W_ALT   = 9.0       # instrument constant in the released archive; also unmetered
RATED_HS      = 500e9     # rated hashrate, H/s (check label/manual)
GPU = {"RTX 3080": (375e6, 320.0, 350, 450), "RTX 3090": (120e6, 350.0, 700, 850)}  # H/s, W, price lo/hi USD
LV06_PRICE    = 40
HOURS_DAY, USD_KWH, YEARS = 8, 0.10, 5
# ---------------------------------------------------

H_PER_SHARE = SHARE_DIFF * 2**32
eff_hs = SHARES * H_PER_SHARE / DURATION_S
print(f"hashes per share              : {H_PER_SHARE:.3e}")
print(f"effective rate                : {eff_hs/1e6:.2f} MH/s")
print(f"efficiency                    : {eff_hs/1e6/POWER_W:.2f} MH/W  (13 W, manuscript)")
print(f"efficiency                    : {eff_hs/1e6/POWER_W_ALT:.2f} MH/W  (9.0 W, archived JSON)")
print(f"energy in run                 : {POWER_W*DURATION_S/3600:.2f} Wh  (13 W)")
print(f"gap vs rated hashrate         : {RATED_HS/eff_hs:,.0f}x")
exp = RATED_HS/H_PER_SHARE
print(f"expected shares/s at rating   : {exp:,.0f}  (~{exp*DURATION_S:,.0f} in run; observed {SHARES})")
print(f"seconds per share on GPU(3080): {H_PER_SHARE/GPU['RTX 3080'][0]:.2f}")
for name,(hs,w,lo,hi) in GPU.items():
    print(f"\n{name}: efficiency {hs/1e6/w:.3f} MH/W -> LV06 is {(eff_hs/1e6/POWER_W)/(hs/1e6/w):.1f}x")
    print(f"  hardware saving: {100*(1-LV06_PRICE/lo):.1f}-{100*(1-LV06_PRICE/hi):.1f}%")
    e_gpu = w*HOURS_DAY*365*USD_KWH/1000
    e_lv  = POWER_W*HOURS_DAY*365*USD_KWH/1000
    print(f"  energy/yr: GPU ${e_gpu:.2f} vs LV06 ${e_lv:.2f}; {YEARS}-yr ${e_gpu*YEARS:.0f} vs ${e_lv*YEARS:.0f}")
    t_gpu=(lo+e_gpu*YEARS, hi+e_gpu*YEARS); t_lv=LV06_PRICE+e_lv*YEARS
    print(f"  5-yr TCO: GPU ${t_gpu[0]:,.0f}-{t_gpu[1]:,.0f} vs LV06 ${t_lv:.0f} ({100*(1-t_lv/t_gpu[0]):.1f}-{100*(1-t_lv/t_gpu[1]):.1f}% lower)")
