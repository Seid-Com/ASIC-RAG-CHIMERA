#!/usr/bin/env python3
"""
pow_verify.py -- independent proof-of-work verification core for the LV06 run.

Why this file exists
--------------------
The original bridge "verified" a share by recomputing its own commitment:

    block_hash = SHA256(merkle_root || ":" || nonce)

That proves only that the bridge can reproduce a string it wrote itself. It says
nothing about whether the device hashed anything, and the manuscript reports it
as a limitation (Section 4.8).

This module performs the check the manuscript says is missing:

    header = version || prevhash || merkle_root || ntime || nbits || nonce   (80 B)
    SHA256d(header) <= target,      target = DIFF1_TARGET / share_difficulty

The medical Merkle root is carried in the header's prevhash field, so a share
that passes is proof of work on a header that contains the root. That is a
record-to-work binding at the byte level, not a self-consistency check.

Byte-order caveat
-----------------
Stratum implementations disagree about the byte order of the prevhash field.
Rather than assume, verification tries three variants and reports which one (if
any) satisfies the target:

    as_sent        bytes exactly as transmitted
    word_swap      reverse bytes within each 4-byte word
    full_reverse   reverse all 32 bytes

The matching variant is recorded per share. If no variant matches, the share is
reported as NOT VERIFIED -- never silently accepted.

Usage
-----
    python pow_verify.py --self-test
    python pow_verify.py results.json [--mode auto|as_sent|word_swap|full_reverse]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

# Bitcoin difficulty-1 target: 0x00000000FFFF0000...0000
DIFF1_TARGET = 0xFFFF << (8 * (0x1D - 3))

# Ground-truth vector used by --self-test. Header serialisation, hash byte order
# and target comparison are all checked against this, so the verifier is anchored
# to something other than its own output.
GENESIS = {
    "version": 1,
    "prevhash": "00" * 32,
    "merkle_root": "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a",
    "ntime": 1231006505,
    "nbits": "1d00ffff",
    "nonce": 2083236893,
    "header_hex": (
        "0100000000000000000000000000000000000000000000000000000000000000"
        "000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa"
        "4b1e5e4a29ab5f49ffff001d1dac2b7c"
    ),
    "hash_hex": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
}

MODES = ("as_sent", "word_swap", "full_reverse")


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hex_int(value) -> int:
    """Stratum numeric fields (nonce, ntime, version, nbits) are always hex.

    A decimal parse would silently misread "00001913" (0x1913) as 1913, which
    is why no share field goes through int(x, 10).
    """
    if isinstance(value, int):
        return value
    if value is None:
        return 0
    text = str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if text == "":
        return 0
    return int(text, 16)


def hex_bytes(value, size: Optional[int] = None, pad: bytes = b"\x00") -> bytes:
    """Decode hex, left-padding or truncating to `size` bytes if given."""
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if size is None:
            return raw
        return raw[-size:] if len(raw) > size else raw.rjust(size, pad)
    text = "" if value is None else str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if len(text) % 2:
        text = "0" + text
    raw = bytes.fromhex(text) if text else b""
    if size is None:
        return raw
    if len(raw) > size:
        return raw[-size:]
    return raw.rjust(size, pad)


def le32(value) -> bytes:
    return struct.pack("<I", hex_int(value) & 0xFFFFFFFF)


def target_from_difficulty(difficulty: float) -> int:
    if difficulty <= 0:
        raise ValueError("share difficulty must be > 0")
    return int(DIFF1_TARGET / difficulty)


def target_from_nbits(nbits) -> int:
    raw = hex_int(nbits)
    exponent = raw >> 24
    mantissa = raw & 0xFFFFFF
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


def hash_int(digest: bytes) -> int:
    """Bitcoin compares the double-SHA256 digest as a little-endian integer."""
    return int.from_bytes(digest, "little")


# ---------------------------------------------------------------------------
# Header construction
# ---------------------------------------------------------------------------

def merkle_root_from_coinbase(coinb1, extranonce1, extranonce2, coinb2,
                              branches) -> bytes:
    """Standard Stratum coinbase -> merkle root."""
    coinbase = (
        hex_bytes(coinb1)
        + hex_bytes(extranonce1)
        + hex_bytes(extranonce2)
        + hex_bytes(coinb2)
    )
    root = sha256d(coinbase)
    for branch in branches or []:
        root = sha256d(root + hex_bytes(branch, 32))
    return root


def prevhash_variants(prevhash_hex) -> Dict[str, bytes]:
    raw = hex_bytes(prevhash_hex, 32)
    return {
        "as_sent": raw,
        "word_swap": b"".join(raw[i:i + 4][::-1] for i in range(0, 32, 4)),
        "full_reverse": raw[::-1],
    }


def build_header(version, prevhash: bytes, merkle_root: bytes, ntime, nbits,
                 nonce) -> bytes:
    header = b"".join([
        le32(version),
        hex_bytes(prevhash, 32),
        hex_bytes(merkle_root, 32),
        le32(ntime),
        le32(nbits),
        le32(nonce),
    ])
    if len(header) != 80:
        raise ValueError(f"header must be 80 bytes, got {len(header)}")
    return header


# ---------------------------------------------------------------------------
# Share verification
# ---------------------------------------------------------------------------

def verify_share(job: dict, share: dict, difficulty: float,
                 modes=MODES) -> dict:
    """
    Rebuild the header for one submitted share and test it against the target.

    `job` carries the fields the bridge sent in mining.notify; `share` carries
    the fields the device returned in mining.submit. Nothing produced by the
    bridge's own hash bookkeeping is trusted here.
    """
    extranonce1 = job.get("extranonce1", "")
    extranonce2 = share.get("extranonce2", job.get("extranonce2", ""))
    ntime = share.get("ntime") or job.get("ntime")
    nonce = share.get("nonce")

    root = merkle_root_from_coinbase(
        job.get("coinb1", ""),
        extranonce1,
        extranonce2,
        job.get("coinb2", ""),
        job.get("merkle_branches") or [],
    )

    target = target_from_difficulty(difficulty)
    nbits_target = target_from_nbits(job.get("nbits", "1d00ffff"))

    attempts = {}
    matched = None
    for mode in modes:
        prevhash = prevhash_variants(job.get("prevhash", ""))[mode]
        header = build_header(
            job.get("version", "20000000"), prevhash, root, ntime,
            job.get("nbits", "1d00ffff"), nonce,
        )
        digest = sha256d(header)
        value = hash_int(digest)
        ok = value <= target
        attempts[mode] = {
            "header_hex": header.hex(),
            "sha256d": digest.hex(),
            "sha256d_le_int_hex": f"{value:064x}",
            "ratio": value / target,
            "ok": ok,
            "meets_nbits_target": value <= nbits_target,
        }
        if ok and matched is None:
            matched = mode

    best = min(attempts.values(), key=lambda a: a["ratio"])
    return {
        "job_id": share.get("job_id", job.get("job_id")),
        "nonce": nonce,
        "difficulty": difficulty,
        "target_hex": f"{target:064x}",
        "nbits_target_hex": f"{nbits_target:064x}",
        "verdict": "verified" if matched else "failed",
        "mode": matched,
        "best_mode": None if matched else min(
            attempts, key=lambda m: attempts[m]["ratio"]),
        "best_ratio": best["ratio"],
        "attempts": attempts,
        "extranonce2": extranonce2,
        "ntime": ntime,
    }


# ---------------------------------------------------------------------------
# Result-file verification (standalone, no imports from the bridge)
# ---------------------------------------------------------------------------

def verify_results(path: Path, modes=MODES) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = {j["job_id"]: j for j in data.get("jobs", [])}
    proofs = data.get("proofs", [])

    difficulty = (
        data.get("experiment", {}).get("share_difficulty")
        or data.get("share_difficulty")
        or (proofs[0].get("difficulty") if proofs else None)
    )

    headerless = [p for p in proofs if not p.get("job_id") or not p.get("nonce")]
    if not jobs:
        return {
            "source": str(path),
            "status": "cannot_verify",
            "reason": (
                "archive records no job registry: mining.notify fields (prevhash, "
                "coinb1/coinb2, version, nbits, ntime, extranonce1) were not saved, "
                "so the 80-byte header cannot be rebuilt. Only the bridge's own "
                "commitment SHA256(merkle_root:nonce) is present."
            ),
            "proofs": len(proofs),
        }
    if difficulty is None:
        return {
            "source": str(path),
            "status": "cannot_verify",
            "reason": "archive records no share difficulty; target unknown",
            "proofs": len(proofs),
        }

    rows = []
    for proof in proofs:
        job = jobs.get(proof.get("job_id"))
        if job is None:
            rows.append({
                "job_id": proof.get("job_id"),
                "verdict": "failed",
                "reason": "job_id not in registry",
            })
            continue
        rows.append(verify_share(job, proof, float(difficulty), modes))

    verified = [r for r in rows if r.get("verdict") == "verified"]
    modes_used: Dict[str, int] = {}
    for row in verified:
        modes_used[row["mode"]] = modes_used.get(row["mode"], 0) + 1

    return {
        "source": str(path),
        "status": "verified" if len(verified) == len(rows) and rows else "failed",
        "share_difficulty": difficulty,
        "proofs": len(rows),
        "verified": len(verified),
        "verification_rate": (len(verified) / len(rows)) if rows else 0.0,
        "prevhash_modes": modes_used,
        "headerless": len(headerless),
        "rows": rows,
    }


def print_report(result: dict, verbose: bool = True) -> None:
    if result.get("status") == "cannot_verify":
        print(f"CANNOT VERIFY  {result['source']}")
        print(f"  reason : {result['reason']}")
        print(f"  proofs : {result['proofs']} (bridge commitments only)")
        return

    print(f"source            : {result['source']}")
    print(f"share difficulty  : {result['share_difficulty']}")
    print(f"shares            : {result['verified']}/{result['proofs']} "
          f"verified ({result['verification_rate'] * 100:.1f}%)")
    print(f"prevhash modes    : {result['prevhash_modes'] or 'none matched'}")
    if verbose:
        print("\n idx  job                     nonce       mode         ratio")
        print(" ---  ----------------------  ----------  -----------  -------")
        for i, row in enumerate(result["rows"]):
            if row.get("verdict") == "verified":
                mode = row["mode"]
                ratio = row["attempts"][mode]["ratio"]
            else:
                mode = f"({row.get('best_mode', '?')})"
                ratio = row.get("best_ratio", float("nan"))
            print(f" {i:3d}  {str(row.get('job_id'))[:22]:<22}  "
                  f"{str(row.get('nonce'))[:10]:<10}  {mode:<11}  {ratio:7.4f}")


# ---------------------------------------------------------------------------
# Self-test: proves the verifier is correct before it is pointed at hardware
# ---------------------------------------------------------------------------

def _mine(version, prevhash: bytes, root: bytes, ntime, nbits, target: int,
          start: int = 0, limit: int = 50_000_000) -> Optional[int]:
    prefix = build_header(version, prevhash, root, ntime, nbits, 0)[:-4]
    for nonce in range(start, start + limit):
        if hash_int(sha256d(prefix + struct.pack("<I", nonce))) <= target:
            return nonce
    return None


def self_test() -> int:
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
        failures += 0 if ok else 1

    print("1. Bitcoin genesis vector (header serialisation + hash order + target)")
    header = build_header(
        GENESIS["version"], hex_bytes(GENESIS["prevhash"]),
        hex_bytes(GENESIS["merkle_root"]), GENESIS["ntime"],
        GENESIS["nbits"], GENESIS["nonce"],
    )
    check("header bytes match", header.hex() == GENESIS["header_hex"])
    digest = sha256d(header)
    check("sha256d matches (display order)", digest[::-1].hex() == GENESIS["hash_hex"])
    check("hash satisfies nbits target",
          hash_int(digest) <= target_from_nbits(GENESIS["nbits"]))
    check("difficulty-1 target matches nbits 0x1d00ffff",
          target_from_difficulty(1.0) == DIFF1_TARGET == target_from_nbits("1d00ffff"))

    print("2. Mine a synthetic share, then verify it")
    job = {
        "job_id": "selftest-000001",
        "prevhash": "ab" * 32,
        "coinb1": "01000000" + "01" + "00" * 32 + "ffffffff",
        "extranonce1": "08000002",
        "coinb2": "ffffffff0100f2052a01000000",
        "merkle_branches": [],
        "version": "20000000",
        "nbits": "1d00ffff",
        "ntime": 0x60000000,
    }
    difficulty = 2e-5
    target = target_from_difficulty(difficulty)
    root = merkle_root_from_coinbase(job["coinb1"], job["extranonce1"], "00000000",
                                     job["coinb2"], [])
    nonce = _mine(job["version"], prevhash_variants(job["prevhash"])["as_sent"],
                  root, job["ntime"], job["nbits"], target)
    check("found a nonce", nonce is not None, f"nonce={nonce}")
    share = {"job_id": job["job_id"], "extranonce2": "00000000",
             "ntime": job["ntime"], "nonce": f"{nonce:08x}" if nonce is not None else "0"}
    result = verify_share(job, share, difficulty, modes=("as_sent",))
    check("valid share verifies", result["verdict"] == "verified",
          f"ratio={result['best_ratio']:.4f}")

    print("3. Tampering is detected")
    bad = dict(share, nonce=f"{(nonce or 0) ^ 0xFFFFFFFF:08x}")
    check("wrong nonce fails",
          verify_share(job, bad, difficulty, modes=("as_sent",))["verdict"] == "failed")
    bad_job = dict(job, prevhash="cd" * 32)
    check("wrong prevhash fails",
          verify_share(bad_job, share, difficulty, modes=("as_sent",))["verdict"] == "failed")
    check("harder difficulty fails",
          verify_share(job, share, difficulty * 1e6, modes=("as_sent",))["verdict"] == "failed")

    print("4. prevhash byte-order detection (firmware convention is unknown)")
    ordered = dict(job, prevhash="".join(f"{i:02x}" for i in range(32)))
    root_o = merkle_root_from_coinbase(ordered["coinb1"], ordered["extranonce1"],
                                       "00000000", ordered["coinb2"], [])
    for mode in MODES:
        n = _mine(ordered["version"], prevhash_variants(ordered["prevhash"])[mode],
                  root_o, ordered["ntime"], ordered["nbits"], target)
        s = {"job_id": ordered["job_id"], "extranonce2": "00000000",
             "ntime": ordered["ntime"], "nonce": f"{n:08x}" if n is not None else "0"}
        r = verify_share(ordered, s, difficulty)
        check(f"detects {mode}", r["mode"] == mode, f"got {r['mode']}")

    print("\nSELF-TEST " + ("PASSED" if failures == 0 else f"FAILED ({failures})"))
    return 0 if failures == 0 else 1


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", nargs="?", type=Path, help="results JSON to verify")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mode", default="auto",
                        choices=("auto",) + MODES,
                        help="prevhash byte order; auto tries all three")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    if args.self_test or args.results is None:
        return self_test()

    modes = MODES if args.mode == "auto" else (args.mode,)
    result = verify_results(args.results, modes)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)

    if result["status"] == "cannot_verify":
        return 3
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
