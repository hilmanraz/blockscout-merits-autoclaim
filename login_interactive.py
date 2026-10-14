#!/usr/bin/env python3
"""
Login interaktif Blockscout Merits — private key TIDAK pernah masuk history shell,
TIDAK di-log, TIDAK ditulis ke disk. Hanya menghasilkan tokens.json.

Jalankan sendiri di SSH:
    python3 login_interactive.py

Setelah selesai, privkey sudah tidak dibutuhkan lagi (token valid ~365 hari).
"""
from __future__ import annotations

import getpass
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))

from claim import _req, BASE, siwe_message, save_token, jwt_exp, log  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("  Blockscout Merits — login (tanda tangan sekali)")
    print("=" * 60)
    print("Private key tidak akan ditampilkan, tidak disimpan,")
    print("dan tidak masuk ke history shell.\n")

    key = getpass.getpass("Tempel private key (0x...), lalu Enter: ").strip()
    if not key:
        print("Dibatalkan.")
        return 1

    from eth_account import Account
    from eth_account.messages import encode_defunct

    if not key.startswith("0x"):
        key = "0x" + key

    try:
        acct = Account.from_key(key)
    except Exception as e:
        print(f"Private key tidak valid: {e}")
        return 1

    addr = acct.address
    print(f"\nWallet  : {addr}")
    print("Menandatangani SIWE + login...")

    st, nonce = _req(f"{BASE}/auth/nonce?blockscout_login_address={addr}"
                     f"&blockscout_login_chain_id=1")
    if st != 200 or not isinstance(nonce, dict):
        print(f"Gagal ambil nonce ({st}). Coba lagi.")
        return 1

    msg = siwe_message(addr, nonce["nonce"], nonce["merits_login_nonce"])
    sig = Account.sign_message(encode_defunct(text=msg), private_key=key).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig

    st, login = _req(f"{BASE}/auth/login",
                     json.dumps({"nonce": nonce["nonce"], "message": msg,
                                 "signature": sig}).encode())
    token = login.get("token") if isinstance(login, dict) else None
    if st != 200 or not token:
        print(f"Login gagal ({st}).")
        return 1

    exp = jwt_exp(token)
    save_token(addr, token, exp)
    days = round((exp - time.time()) / 86400, 1) if exp else 0
    print(f"\n✅ Login berhasil.")
    print(f"   Token tersimpan di tokens.json (chmod 600)")
    print(f"   Valid ~{days} hari")
    print(f"   Private key sudah tidak diperlukan lagi.")
    print("\nLangkah berikutnya:")
    print("   python3 claim.py --status     # cek saldo & streak")
    print("   python3 claim.py              # claim hari ini")
    return 0


if __name__ == "__main__":
    sys.exit(main())
