#!/usr/bin/env python3
"""
bridge_pow.py -- Stratum bridge that verifies proof-of-work instead of only
recomputing its own commitment.

Differences from the bridge that produced the published numbers
(archive/REAL_DATA_LV06/chimera_handoff/NEW/DEFINITIVE_ASIC_RAG_EXPERIMENT.py):

1. Job registry. Every mining.notify is stored: job_id, prevhash (the medical
   Merkle root), coinb1/coinb2, branches, version, nbits, ntime, extranonce1.
   The old bridge kept only `current_merkle_root`, so a share arriving after a
   job switch was attributed to the wrong root.

2. Job attribution on submit. `mining.submit` params are parsed as
   [worker, job_id, extranonce2, ntime, nonce] and the share is bound to the
   job that produced it, not to whatever root happens to be current.

3. Real verification. Each share's 80-byte header is rebuilt and SHA256d tested
   against the share target. The verdict is recorded per share; it is never
   assumed. See pow_verify.py.

4. Complete archive. Every share is kept, not `all_proofs[:10]`, and is appended
   to proofs.jsonl as it arrives so a crash cannot truncate the record. The raw
   Stratum traffic is written to a log for independent replay.

A share that fails verification is still recorded and answered with success by
default (Config.REQUIRE_POW=False), because rejecting shares would change the
device's behaviour mid-run. Flip it to True only when you want the strict mode.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from pow_verify import sha256d, verify_share

# Matches the original bridge, so a v2 run is comparable with the v1 run.
EXTRANONCE1 = "08000002"
EXTRANONCE2_SIZE = 4
VERSION_HEX = "20000000"
NBITS_HEX = "1d00ffff"
COINB1 = (
    "010000000100000000000000000000000000000000000000000000000000000000"
    "00000000ffffffff"
)
COINB2 = (
    "ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae139"
    "0813a627c66fb8be7947be63c52da7589379515d4e0a604f8141781e62294721166b"
    "f621e73a82cbf2342c858eeac00000000"
)


@dataclass
class Job:
    job_id: str
    merkle_root: str          # medical root, as supplied by the caller
    prevhash: str             # bytes actually sent in mining.notify
    records_count: int
    version: str
    nbits: str
    ntime: str
    coinb1: str
    coinb2: str
    extranonce1: str
    merkle_branches: List[str] = field(default_factory=list)
    created_at: float = 0.0


class PoWBridge:
    """Stratum bridge with a job registry and per-share PoW verification."""

    REQUIRE_POW = False

    def __init__(self,
                 difficulty: float = 0.08,
                 prevhash_mode: str = "as_sent",
                 host: str = "0.0.0.0",
                 stratum_port: int = 3333,
                 api_port: int = 4029,
                 outdir: Optional[Path] = None,
                 on_proof: Optional[Callable[[dict], None]] = None):
        self.difficulty = float(difficulty)
        self.prevhash_mode = prevhash_mode
        self.on_proof = on_proof
        self.outdir = Path(outdir) if outdir else Path.cwd()
        self.outdir.mkdir(parents=True, exist_ok=True)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, stratum_port))
        self.sock.listen(5)

        self.api_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.api_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.api_sock.bind((host, api_port))
        self.api_sock.listen(5)

        self.lock = threading.RLock()
        self.jobs: Dict[str, Job] = {}
        self.job_order: List[str] = []
        self.proofs: List[dict] = []
        self.conn: Optional[socket.socket] = None
        self.miner_connected = threading.Event()
        self._job_counter = 0
        self._last_share_at = 0.0
        self._stop = threading.Event()

        self.raw_log = self.outdir / "stratum_raw.jsonl"
        self.proof_log = self.outdir / "proofs.jsonl"
        self.raw_log.touch()
        self.proof_log.touch()

        threading.Thread(target=self._api_loop, daemon=True).start()

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        while not self._stop.is_set():
            try:
                conn, addr = self.sock.accept()
            except OSError:
                return
            print(f"[bridge] miner connected from {addr[0]}:{addr[1]}")
            self.conn = conn
            self.miner_connected.set()
            threading.Thread(target=self._handle_miner, args=(conn,), daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        for s in (self.sock, self.api_sock):
            try:
                s.close()
            except OSError:
                pass

    # -- job registry ------------------------------------------------------
    def _apply_mode(self, root_hex: str) -> str:
        raw = bytes.fromhex(root_hex)
        if self.prevhash_mode == "word_swap":
            return b"".join(raw[i:i + 4][::-1] for i in range(0, 32, 4)).hex()
        if self.prevhash_mode == "full_reverse":
            return raw[::-1].hex()
        return raw.hex()

    def seal(self, merkle_root: str, records_count: int) -> str:
        """Register a new job carrying `merkle_root` and push it to the miner."""
        with self.lock:
            self._job_counter += 1
            job = Job(
                job_id=f"med_block_{self._job_counter:06d}",
                merkle_root=merkle_root,
                prevhash=self._apply_mode(merkle_root),
                records_count=records_count,
                version=VERSION_HEX,
                nbits=NBITS_HEX,
                ntime=hex(int(time.time()))[2:],
                coinb1=COINB1,
                coinb2=COINB2,
                extranonce1=EXTRANONCE1,
                merkle_branches=[],
                created_at=time.time(),
            )
            self.jobs[job.job_id] = job
            self.job_order.append(job.job_id)
        if self.conn:
            self._send_job(self.conn, job)
        return job.job_id

    def _send_job(self, conn: socket.socket, job: Job) -> None:
        msg = {
            "id": None,
            "method": "mining.notify",
            "params": [
                job.job_id, job.prevhash, job.coinb1, job.coinb2,
                job.merkle_branches, job.version, job.nbits, job.ntime, True,
            ],
        }
        self._send(conn, msg)

    # -- protocol ----------------------------------------------------------
    def _handle_miner(self, conn: socket.socket) -> None:
        buffer = ""
        while not self._stop.is_set():
            try:
                chunk = conn.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.strip():
                    try:
                        self._process(json.loads(line), conn)
                    except json.JSONDecodeError:
                        self._raw("rx_bad", line)
        print("[bridge] miner disconnected")

    def _process(self, msg: dict, conn: socket.socket) -> None:
        self._raw("rx", msg)
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "mining.subscribe":
            self._send(conn, {
                "id": msg_id,
                "result": [[["mining.set_difficulty", "1"], ["mining.notify", "1"]],
                           EXTRANONCE1, EXTRANONCE2_SIZE],
                "error": None,
            })
        elif method == "mining.authorize":
            self._send(conn, {"id": msg_id, "result": True, "error": None})
            self._send(conn, {"id": None, "method": "mining.set_difficulty",
                              "params": [self.difficulty]})
            with self.lock:
                latest = self.jobs.get(self.job_order[-1]) if self.job_order else None
            if latest:
                self._send_job(conn, latest)
        elif method == "mining.submit":
            self._handle_submit(msg, conn)

    def _handle_submit(self, msg: dict, conn: socket.socket) -> None:
        params = msg.get("params") or []
        share = {
            "job_id": params[1] if len(params) > 1 else None,
            "extranonce2": params[2] if len(params) > 2 else "",
            "ntime": params[3] if len(params) > 3 else None,
            "nonce": params[4] if len(params) > 4 else None,
            "submit_params": params,
            "received_at": time.time(),
        }

        with self.lock:
            job = self.jobs.get(share["job_id"])
            if job is None:
                verdict = {"verdict": "failed", "reason": "unknown job_id"}
            else:
                verdict = verify_share(asdict(job), share, self.difficulty)
            now = share["received_at"]
            interval = (now - self._last_share_at) if self._last_share_at else None
            self._last_share_at = now

            proof = {
                "index": len(self.proofs),
                "job_id": share["job_id"],
                "merkle_root": job.merkle_root if job else None,
                "records_count": job.records_count if job else 0,
                "nonce": share["nonce"],
                "extranonce2": share["extranonce2"],
                "ntime": share["ntime"],
                "submit_params": share["submit_params"],
                "received_at": now,
                "interval_s": interval,
                # kept so the old 23/23 style check can still be reproduced
                "bridge_commitment": (
                    hashlib.sha256(
                        f"{job.merkle_root}:{share['nonce']}".encode()
                    ).hexdigest() if job else None
                ),
                "pow": verdict,
            }
            self.proofs.append(proof)
            count = len(self.proofs)
            with self.proof_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(proof) + "\n")

        ok = proof["pow"].get("verdict") == "verified"
        mode = proof["pow"].get("mode")
        print(f"[bridge] share #{count:03d} job={proof['job_id']} "
              f"nonce={proof['nonce']} pow={'OK' if ok else 'FAIL'}"
              f"{'' if mode is None else ' via ' + mode}")
        self._raw("tx", {
            "id": msg.get("id"), "result": True if ok or not self.REQUIRE_POW else False,
            "error": None if ok or not self.REQUIRE_POW else [23, "low-level pow", None],
        })
        self._send(conn, {
            "id": msg.get("id"),
            "result": True if ok or not self.REQUIRE_POW else False,
            "error": None if ok or not self.REQUIRE_POW else [23, "low-level pow", None],
        })
        if self.on_proof:
            self.on_proof(proof)

    def _send(self, conn: socket.socket, data: dict) -> None:
        self._raw("tx", data)
        try:
            conn.sendall((json.dumps(data) + "\n").encode())
        except OSError:
            pass

    def _raw(self, direction: str, payload) -> None:
        entry = {"t": time.time(), "dir": direction, "msg": payload}
        with self.raw_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    # -- API ---------------------------------------------------------------
    def _api_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.api_sock.accept()
            except OSError:
                return
            try:
                cmd = conn.recv(1024).decode().strip()
                if cmd == "GET_STATS":
                    conn.sendall(json.dumps(self.stats()).encode())
                elif cmd == "GET_PROOFS":
                    with self.lock:
                        conn.sendall(json.dumps(self.proofs).encode())
                elif cmd == "GET_JOBS":
                    with self.lock:
                        conn.sendall(json.dumps(
                            [asdict(j) for j in self.jobs.values()]).encode())
                elif cmd == "RESET":
                    with self.lock:
                        self.proofs.clear()
                        self._last_share_at = 0.0
                    conn.sendall(b"OK")
            except OSError:
                pass
            finally:
                conn.close()

    def stats(self) -> dict:
        with self.lock:
            verified = sum(1 for p in self.proofs
                           if p["pow"].get("verdict") == "verified")
            return {
                "shares": len(self.proofs),
                "pow_verified": verified,
                "pow_failed": len(self.proofs) - verified,
                "jobs": len(self.jobs),
                "last_share_at": self._last_share_at,
            }

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "jobs": [asdict(j) for j in self.jobs.values()],
                "proofs": list(self.proofs),
            }
