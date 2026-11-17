#!/usr/bin/env python3
"""
run_v2.py -- LV06 anchoring run with per-share proof-of-work verification.

Reuses the record generator and Merkle tree from the original experiment
(read-only, unmodified) and replaces the instrument: PoWBridge records every
job and every share, rebuilds each 80-byte header, and tests it against the
share target.

    python run_v2.py --duration 300 --power 13.0 --power-source nameplate
    python run_v2.py --simulate --duration 20      # no hardware, end-to-end check

Outputs (in --outdir, default ./runs):
    results_v2_<epoch>.json   metrics + full job registry + every share
    proofs.jsonl              append-only, one line per share
    stratum_raw.jsonl         every Stratum message in both directions
    run_manifest.json         argv, power basis, environment

Power basis is recorded, never inferred. --power-source nameplate means the
efficiency number is derived, exactly like the published 2.03 MH/W.
--power-source meter means it is derived from a measured reading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import statistics
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[1] / "archive" / "REAL_DATA_LV06" / "chimera_handoff" / "NEW"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ARCHIVE))

from bridge_pow import PoWBridge                                   # noqa: E402
from pow_verify import (hash_int, merkle_root_from_coinbase,        # noqa: E402
                        prevhash_variants, sha256d, target_from_difficulty)

# Original experiment module: data generation only. Nothing in it is modified.
from DEFINITIVE_ASIC_RAG_EXPERIMENT import (  # noqa: E402
    Config, MedicalRecordGenerator, MerkleTree)


# ---------------------------------------------------------------------------
# Simulated miner (no hardware): speaks Stratum, mines at an easy target
# ---------------------------------------------------------------------------

class SimulatedMiner(threading.Thread):
    def __init__(self, host: str, port: int, period: float = 0.6):
        super().__init__(daemon=True)
        self.host, self.port, self.period = host, port, period
        self.stop_flag = threading.Event()
        self.job = None
        self.difficulty = None
        self.shares = 0
        self._buf = ""

    def _send(self, sock, obj):
        sock.sendall((json.dumps(obj) + "\n").encode())

    def run(self):
        sock = socket.create_connection((self.host, self.port), timeout=10)
        sock.settimeout(0.5)
        self._send(sock, {"id": 1, "method": "mining.subscribe", "params": ["sim/1.0"]})
        self._send(sock, {"id": 2, "method": "mining.authorize",
                          "params": ["sim", "x"]})
        last_share = 0.0
        while not self.stop_flag.is_set():
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                chunk = b""
            if chunk:
                self._buf += chunk.decode()
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    if msg.get("method") == "mining.notify":
                        p = msg["params"]
                        self.job = {"job_id": p[0], "prevhash": p[1], "coinb1": p[2],
                                    "coinb2": p[3], "branches": p[4], "version": p[5],
                                    "nbits": p[6], "ntime": p[7]}
                    elif msg.get("method") == "mining.set_difficulty":
                        self.difficulty = float(msg["params"][0])
            if self.job and self.difficulty and time.time() - last_share >= self.period:
                nonce = self._mine(start=(self.shares + 1) * 100_000)
                if nonce is not None:
                    self._send(sock, {
                        "id": 100 + self.shares, "method": "mining.submit",
                        "params": ["sim", self.job["job_id"], "00000000",
                                   self.job["ntime"], f"{nonce:08x}"],
                    })
                    self.shares += 1
                last_share = time.time()
        sock.close()

    def _mine(self, start: int = 0, limit: int = 5_000_000):
        job = self.job
        target = target_from_difficulty(self.difficulty)
        root = merkle_root_from_coinbase(job["coinb1"], "08000002", "00000000",
                                         job["coinb2"], job["branches"])
        prevhash = prevhash_variants(job["prevhash"])["as_sent"]
        prefix = (int(job["version"], 16).to_bytes(4, "little") + prevhash + root
                  + int(job["ntime"], 16).to_bytes(4, "little")
                  + int(job["nbits"], 16).to_bytes(4, "little"))
        for nonce in range(start, start + limit):
            if hash_int(sha256d(prefix + nonce.to_bytes(4, "little"))) <= target:
                return nonce
        return None


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

def run(args) -> dict:
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    generator = MedicalRecordGenerator()
    records = []
    for _ in range(args.patients):
        records.extend(generator.generate_patient_records(Config.RECORDS_PER_PATIENT))
    batch_size = Config.RECORDS_PER_PATIENT
    print(f"[run] {len(records)} records, {args.patients} patients, "
          f"{args.difficulty} share difficulty")

    bridge = PoWBridge(
        difficulty=args.difficulty,
        prevhash_mode=args.prevhash_mode,
        stratum_port=args.stratum_port,
        api_port=args.api_port,
        outdir=outdir,
    )
    threading.Thread(target=bridge.start, daemon=True).start()

    miner = None
    if args.simulate:
        if args.difficulty > 1e-4:
            print("[run] simulation forces an easy target; using 1e-6")
            args.difficulty = 1e-6
        bridge.difficulty = args.difficulty
        miner = SimulatedMiner("127.0.0.1", args.stratum_port)
        miner.start()

    if not bridge.miner_connected.wait(timeout=args.connect_timeout):
        bridge.stop()
        raise SystemExit(f"no miner connected within {args.connect_timeout}s")

    start = time.time()
    interval = args.duration / args.patients
    idx = 0
    last = start
    while time.time() - start < args.duration and idx < len(records):
        if time.time() - last >= interval:
            batch = records[idx:idx + batch_size]
            tree = MerkleTree(batch)
            bridge.seal(tree.get_root_hex(), len(batch))
            idx += batch_size
            last = time.time()
        time.sleep(0.05)

    # Let in-flight shares land before closing the books.
    time.sleep(args.drain)
    duration = time.time() - start
    if miner:
        miner.stop_flag.set()
    bridge.stop()

    snap = bridge.snapshot()
    return summarise(args, snap, duration, started, outdir)


def summarise(args, snap, duration, started, outdir) -> dict:
    jobs, proofs = snap["jobs"], snap["proofs"]
    difficulty = args.difficulty

    hashes_per_share = difficulty * (2 ** 32)
    effective_hs = len(proofs) * hashes_per_share / duration if duration else 0
    efficiency = (effective_hs / 1e6) / args.power if args.power else 0
    energy_wh = args.power * duration / 3600

    intervals = [p["interval_s"] for p in proofs if p.get("interval_s")]
    lat = {
        "mean": statistics.mean(intervals) if intervals else 0,
        "p50": statistics.median(intervals) if intervals else 0,
        "p95": sorted(intervals)[max(0, int(len(intervals) * 0.95) - 1)] if intervals else 0,
        "p99": sorted(intervals)[max(0, int(len(intervals) * 0.99) - 1)] if intervals else 0,
        "stdev": statistics.stdev(intervals) if len(intervals) > 1 else 0,
        "cv": (statistics.stdev(intervals) / statistics.mean(intervals)
               if len(intervals) > 1 and statistics.mean(intervals) else 0),
        "n": len(intervals),
    }
    peak_hs = (hashes_per_share / min(intervals)) if intervals and min(intervals) > 0 else 0

    verified = [p for p in proofs if p["pow"].get("verdict") == "verified"]
    modes = {}
    for p in verified:
        modes[p["pow"]["mode"]] = modes.get(p["pow"]["mode"], 0) + 1
    commitment_ok = sum(
        1 for p in proofs
        if p["bridge_commitment"] and hashlib.sha256(
            f"{p['merkle_root']}:{p['nonce']}".encode()).hexdigest() == p["bridge_commitment"])

    gpu = {"RTX 3080": (375e6, 320.0, 350, 450),
           "RTX 3090": (120e6, 350.0, 700, 850)}
    gpu_out = {}
    for name, (hs, watts, lo, hi) in gpu.items():
        gpu_eff = hs / 1e6 / watts
        e_year = watts * args.hours_day * 365 * args.usd_kwh / 1000
        e_lv06 = args.power * args.hours_day * 365 * args.usd_kwh / 1000
        gpu_out[name] = {
            "efficiency_mhw": gpu_eff,
            "lv06_multiple": (efficiency / gpu_eff) if gpu_eff else 0,
            "energy_year_usd": e_year,
            "lv06_energy_year_usd": e_lv06,
            "tco5_gpu_usd": [lo + e_year * args.years, hi + e_year * args.years],
            "tco5_lv06_usd": args.lv06_price + e_lv06 * args.years,
        }

    result = {
        "schema": "asic-rag-pow-v2",
        "experiment": {
            "started_at": started,
            "duration_seconds": duration,
            "share_difficulty": difficulty,
            "difficulty_source": "cli",
            "prevhash_mode": args.prevhash_mode,
            "power_watts": args.power,
            "power_source": args.power_source,
            "efficiency_basis": f"derived_from_{args.power_source}_power",
            "rated_hashrate_hs": args.rated_hs,
            "records": args.patients * Config.RECORDS_PER_PATIENT,
            "patients": args.patients,
            "jobs_sealed": len(jobs),
            "shares": len(proofs),
            "host": platform.node(),
            "python": platform.python_version(),
            "simulated": bool(args.simulate),
        },
        "metrics": {
            "effective_hashrate_mhs": effective_hs / 1e6,
            "efficiency_mhw": efficiency,
            "energy_wh": energy_wh,
            "gap_vs_rated": (args.rated_hs / effective_hs) if effective_hs else None,
            "peak_implied_hashrate_mhs": peak_hs / 1e6,
            "inter_share": lat,
            "gpu": gpu_out,
        },
        "verification": {
            "shares": len(proofs),
            "pow_verified": len(verified),
            "pow_failed": len(proofs) - len(verified),
            "pow_verification_rate": (len(verified) / len(proofs)) if proofs else 0,
            "prevhash_modes": modes,
            "bridge_commitment_consistent": commitment_ok,
            "bridge_commitment_checked": sum(1 for p in proofs if p["bridge_commitment"]),
            "job_attribution_unknown": sum(
                1 for p in proofs if p["pow"].get("reason") == "unknown job_id"),
        },
        "jobs": jobs,
        "proofs": proofs,
    }

    manifest = {
        "argv": sys.argv,
        "cwd": os.getcwd(),
        "started_at": started,
        "power_watts": args.power,
        "power_source": args.power_source,
        "difficulty": difficulty,
        "prevhash_mode": args.prevhash_mode,
        "archive_module": str(ARCHIVE),
    }
    (outdir / "run_manifest.json").write_text(json.dumps(manifest, indent=2),
                                              encoding="utf-8")
    path = outdir / f"results_v2_{int(started)}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    result["_path"] = str(path)
    return result


def report(result: dict) -> None:
    e = result["experiment"]
    m = result["metrics"]
    v = result["verification"]
    print("\n" + "=" * 72)
    print("LV06 ANCHORING RUN (v2, per-share PoW verification)")
    print("=" * 72)
    print(f"  duration            : {e['duration_seconds']:.2f} s"
          f"{'   [SIMULATED]' if e['simulated'] else ''}")
    print(f"  jobs sealed         : {e['jobs_sealed']}")
    print(f"  shares              : {e['shares']}")
    print(f"  PoW verified        : {v['pow_verified']}/{v['shares']}"
          f"  ({v['pow_verification_rate'] * 100:.1f}%)"
          f"  modes={v['prevhash_modes'] or 'none'}")
    print(f"  bridge commitment   : {v['bridge_commitment_consistent']}"
          f"/{v['bridge_commitment_checked']} consistent (old-style check)")
    print(f"  effective hashrate  : {m['effective_hashrate_mhs']:.2f} MH/s")
    print(f"  efficiency          : {m['efficiency_mhw']:.2f} MH/W"
          f"  [{e['efficiency_basis']}, {e['power_watts']} W]")
    print(f"  energy in run       : {m['energy_wh']:.2f} Wh")
    if m["gap_vs_rated"]:
        print(f"  gap vs rated        : {m['gap_vs_rated']:,.0f}x")
    print(f"  inter-share mean    : {m['inter_share']['mean']:.2f} s"
          f"  (n={m['inter_share']['n']})")
    for name, g in m["gpu"].items():
        print(f"  vs {name:<10}      : {g['lv06_multiple']:.1f}x efficiency"
              f"  5-yr TCO ${g['tco5_lv06_usd']:.0f} vs "
              f"${g['tco5_gpu_usd'][0]:,.0f}-{g['tco5_gpu_usd'][1]:,.0f}")
    if v["shares"] and v["pow_verified"] == 0:
        print("\n  NOTE: no share satisfied the target under any header layout.")
        print("  The run is still valid as a share-rate measurement, but it does")
        print("  NOT establish record-to-work binding. See experiment/README_v2.md.")
    print(f"\n  results: {result.get('_path')}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--duration", type=float, default=300)
    p.add_argument("--patients", type=int, default=50)
    p.add_argument("--difficulty", type=float, default=Config.BLOCK_DIFFICULTY)
    p.add_argument("--power", type=float, default=13.0)
    p.add_argument("--power-source", choices=("nameplate", "meter"), default="nameplate")
    p.add_argument("--prevhash-mode", choices=("as_sent", "word_swap", "full_reverse"),
                   default="as_sent")
    p.add_argument("--rated-hs", type=float, default=500e9)
    p.add_argument("--lv06-price", type=float, default=40.0)
    p.add_argument("--hours-day", type=float, default=8.0)
    p.add_argument("--usd-kwh", type=float, default=0.10)
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--stratum-port", type=int, default=3333)
    p.add_argument("--api-port", type=int, default=4029)
    p.add_argument("--outdir", default=str(HERE / "runs"))
    p.add_argument("--connect-timeout", type=float, default=120)
    p.add_argument("--drain", type=float, default=2.0)
    p.add_argument("--simulate", action="store_true",
                   help="run against a built-in Stratum miner (no hardware)")
    args = p.parse_args(argv)

    result = run(args)
    report(result)
    return 0 if result["verification"]["pow_verified"] or args.simulate else 2


if __name__ == "__main__":
    sys.exit(main())
