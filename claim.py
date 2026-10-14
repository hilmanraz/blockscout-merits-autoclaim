#!/usr/bin/env python3
"""
Blockscout Merits — auto daily check-in.

Dua mode:
  A) TOKEN MODE (disarankan) — tanda tangan sekali, simpan JWT (~365 hari).
     Private key TIDAK perlu disimpan. Cron pakai token yang sudah ada.
  B) KEY MODE — simpan private key di wallets.txt; script tanda tangan tiap hari.

Perintah:
  python3 claim.py --login        # tanda tangan sekali (butuh key), simpan token
  python3 claim.py --login --key 0x...   # tanpa simpan key ke disk
  python3 claim.py                # claim harian (pakai token tersimpan)
  python3 claim.py --dry-run      # cek saja
  python3 claim.py --status       # lihat saldo/streak tiap wallet
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://merits.blockscout.com/api/v1"
DIR = Path(__file__).resolve().parent
WALLETS_FILE = DIR / "wallets.txt"
TOKENS_FILE = DIR / "tokens.json"
STATE_FILE = DIR / "state.json"
LOG_FILE = DIR / "claim.log"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _headers(token: str | None = None) -> dict:
    h = {"accept": "*/*", "origin": "https://eth.blockscout.com",
         "referer": "https://eth.blockscout.com/", "user-agent": UA}
    if token:
        h["authorization"] = f"Bearer {token}"
    return h


def _req(url, data=None, token=None, method=None, retries=3):
    last = ""
    for attempt in range(retries):
        try:
            h = _headers(token)
            if data is not None:
                h["content-type"] = "application/json"
            r = urllib.request.urlopen(
                urllib.request.Request(url, data=data, headers=h, method=method), timeout=30)
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw.decode(errors="ignore")[:300]
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")[:300]
            if e.code != 429 and 400 <= e.code < 500:
                return e.code, body
            last = f"HTTP {e.code}: {body}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(3 * (attempt + 1))
    return 0, last or "unknown error"


# ── storage ────────────────────────────────────────────────────────────────
def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, obj) -> None:
    try:
        path.write_text(json.dumps(obj, indent=2))
        path.chmod(0o600)
    except Exception:
        pass


def load_wallets() -> list[str]:
    if not WALLETS_FILE.exists():
        return []
    return [s.strip() for s in WALLETS_FILE.read_text().splitlines()
            if s.strip() and not s.strip().startswith("#")]


def load_tokens() -> dict:
    return _read_json(TOKENS_FILE, {})


def save_token(address: str, token: str, exp: int) -> None:
    toks = load_tokens()
    toks[address.lower()] = {"token": token, "exp": exp}
    _write_json(TOKENS_FILE, toks)


def token_valid(entry: dict, min_days: int = 1) -> bool:
    try:
        return int(entry.get("exp", 0)) > time.time() + min_days * 86400
    except Exception:
        return False


def jwt_exp(token: str) -> int:
    import base64
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return int(json.loads(base64.urlsafe_b64decode(p)).get("exp", 0))
    except Exception:
        return 0


# ── SIWE ───────────────────────────────────────────────────────────────────
def siwe_message(address: str, nonce: str, merits_nonce: str) -> str:
    now = datetime.now(timezone.utc)
    return (
        f"eth.blockscout.com wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"Sign in/up to Blockscout Account V2 & Blockscout Merits program. "
        f"Merits nonce: {merits_nonce}.\n\n"
        f"URI: https://eth.blockscout.com\n"
        f"Version: 1\n"
        f"Chain ID: 1\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {now.isoformat().replace('+00:00', 'Z')}\n"
        f"Expiration Time: {(now + timedelta(days=365)).isoformat().replace('+00:00', 'Z')}"
    )


def do_login(key_raw: str) -> tuple[str | None, str | None, int]:
    """Sign once, get JWT. Returns (address, token, exp)."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    key = key_raw if key_raw.startswith("0x") else "0x" + key_raw
    acct = Account.from_key(key)
    addr = acct.address

    st, nonce = _req(f"{BASE}/auth/nonce?blockscout_login_address={addr}"
                     f"&blockscout_login_chain_id=1")
    if st != 200 or not isinstance(nonce, dict):
        return None, None, 0

    msg = siwe_message(addr, nonce["nonce"], nonce["merits_login_nonce"])
    sig = Account.sign_message(encode_defunct(text=msg), private_key=key).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig

    st, login = _req(f"{BASE}/auth/login",
                     json.dumps({"nonce": nonce["nonce"], "message": msg,
                                 "signature": sig}).encode())
    token = login.get("token") if isinstance(login, dict) else None
    if st != 200 or not token:
        return addr, None, 0
    return addr, token, jwt_exp(token)


# ── core ───────────────────────────────────────────────────────────────────
def process(address: str, token: str, idx: int, total: int, dry_run: bool) -> dict:
    short = f"{address[:6]}...{address[-4:]}"
    res = {"address": address, "claimed": False, "reward": 0, "streak": 0,
           "balance": None, "error": None}

    st, bal = _req(f"{BASE}/user/balances", token=token)
    if st == 401:
        res["error"] = "token expired/invalid — jalankan --login lagi"
        log(f"[{idx}/{total}] {short} FAIL — {res['error']}")
        return res
    if isinstance(bal, dict):
        res["balance"] = bal.get("total")

    st, chk = _req(f"{BASE}/user/daily/check", token=token)
    if st != 200 or not isinstance(chk, dict):
        res["error"] = f"check gagal ({st})"
        log(f"[{idx}/{total}] {short} FAIL — {res['error']}")
        return res

    res["streak"] = int(chk.get("streak") or 0)
    if not chk.get("available"):
        log(f"[{idx}/{total}] {short} OK — sudah claim hari ini "
            f"(streak {res['streak']}, saldo {res['balance']})")
        return res

    if dry_run:
        log(f"[{idx}/{total}] {short} DRY-RUN — bisa claim "
            f"{chk.get('total_reward')} Merits (streak {res['streak']})")
        return res

    st, claim = _req(f"{BASE}/user/daily/claim", data=b"", token=token, method="POST")
    if st == 200 and isinstance(claim, dict):
        res["claimed"] = True
        res["reward"] = int(claim.get("total_reward") or 0)
        res["streak"] = int(claim.get("streak") or res["streak"])
        log(f"[{idx}/{total}] {short} SUCCESS — +{res['reward']} Merits "
            f"| streak {res['streak']} | saldo {res['balance']} → "
            f"{int(res['balance'] or 0) + res['reward']}")
    else:
        res["error"] = f"claim gagal ({st})"
        log(f"[{idx}/{total}] {short} FAIL — {res['error']} {str(claim)[:120]}")
    return res


def cmd_login(args) -> int:
    keys = [args.key] if args.key else load_wallets()
    if not keys:
        log("Tidak ada key. Isi wallets.txt atau pakai --key 0x...")
        return 2
    ok = 0
    for k in keys:
        addr, token, exp = do_login(k)
        if not addr:
            log("login gagal (format key salah)")
            continue
        if not token:
            log(f"{addr[:6]}...{addr[-4:]} login gagal")
            continue
        save_token(addr, token, exp)
        days = round((exp - time.time()) / 86400, 1) if exp else 0
        log(f"{addr[:6]}...{addr[-4:]} LOGIN OK — token tersimpan, valid ~{days} hari")
        ok += 1
    if ok and not args.key:
        log("Saran: setelah ini wallets.txt boleh dikosongkan — token berlaku ~365 hari.")
    return 0 if ok else 1


def cmd_status(args) -> int:
    toks = load_tokens()
    if not toks:
        log("Belum ada token. Jalankan: python3 claim.py --login")
        return 2
    for i, (addr, entry) in enumerate(toks.items(), 1):
        t = entry.get("token")
        st, bal = _req(f"{BASE}/user/balances", token=t)
        st2, chk = _req(f"{BASE}/user/daily/check", token=t)
        bal_s = bal.get("total") if isinstance(bal, dict) else "?"
        avail = chk.get("available") if isinstance(chk, dict) else "?"
        streak = chk.get("streak") if isinstance(chk, dict) else "?"
        log(f"{addr} — saldo {bal_s} | streak {streak} | bisa claim hari ini: {avail}")
    return 0


def cmd_claim(args) -> int:
    toks = load_tokens()
    keys = load_wallets()
    entries: list[tuple[str, str]] = []

    for addr, entry in toks.items():
        if token_valid(entry):
            entries.append((addr, entry["token"]))

    if not entries:
        log("Tidak ada token valid. Jalankan: python3 claim.py --login")
        return 2

    if args.only:
        entries = [entries[args.only - 1]]

    log(f"=== Blockscout Merits check-in | {len(entries)} wallet | "
        f"{'DRY-RUN' if args.dry_run else 'LIVE'} ===")

    results = []
    for i, (addr, token) in enumerate(entries, 1):
        try:
            results.append(process(addr, token, i, len(entries), args.dry_run))
        except Exception as e:
            log(f"[{i}/{len(entries)}] ERROR — {type(e).__name__}: {e}")
            results.append({"address": addr, "claimed": False, "error": str(e)})
        if i < len(entries):
            time.sleep(3)

    claimed = [r for r in results if r.get("claimed")]
    failed = [r for r in results if r.get("error")]
    gained = sum(r.get("reward", 0) for r in claimed)
    summary = (f"Blockscout Merits: {len(claimed)}/{len(entries)} claimed "
               f"(+{gained} Merits), {len(failed)} gagal")
    log(summary)

    st = _read_json(STATE_FILE, {})
    st["last_run"] = datetime.now(timezone.utc).isoformat()
    st["last_summary"] = summary
    st["wallets"] = {r["address"]: {"balance": r.get("balance"),
                                    "streak": r.get("streak"),
                                    "claimed": r.get("claimed"),
                                    "error": r.get("error")} for r in results}
    _write_json(STATE_FILE, st)

    if args.quiet:
        print(summary)
        for r in failed:
            print(f"FAIL {r['address']}: {r['error']}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Blockscout Merits auto daily check-in")
    ap.add_argument("--login", action="store_true", help="tanda tangan sekali, simpan token (~365 hari)")
    ap.add_argument("--key", help="private key untuk --login (tanpa simpan ke disk)")
    ap.add_argument("--status", action="store_true", help="lihat saldo & streak")
    ap.add_argument("--dry-run", action="store_true", help="cek saja, jangan claim")
    ap.add_argument("--only", type=int, help="proses wallet ke-N saja")
    ap.add_argument("--quiet", action="store_true", help="hanya ringkasan (buat cron)")
    args = ap.parse_args()

    if args.login:
        return cmd_login(args)
    if args.status:
        return cmd_status(args)
    return cmd_claim(args)


if __name__ == "__main__":
    sys.exit(main())
