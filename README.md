# Blockscout Merits — Auto Daily Check-In

Automate the [Blockscout Merits](https://merits.blockscout.com/) daily claim (**+10 Merits/day**) without opening a browser.

Pure Python. No browser, no Playwright, no headless Chrome. Multi-wallet, retry logic, cron-ready.

```
nonce → sign SIWE message → JWT (~365 days) → daily check → daily claim
```

---

## TL;DR — 3 commands

```bash
git clone https://github.com/hilmanraz/blockscout-merits-autoclaim.git
cd blockscout-merits-autoclaim
pip install eth-account
```

Then:

```bash
python3 login_interactive.py     # 1. sign in once (your private key stays on your machine)
python3 claim.py --dry-run       # 2. check if there's anything to claim
python3 claim.py                 # 3. claim it
```

That's it. Run step 3 daily, or let cron do it for you (see [Scheduling](#scheduling)).

---

## What it actually does

Blockscout gives you **10 free Merits every day** — but only if you visit the dashboard and click claim. Miss a day and your streak resets.

This tool does the clicking for you:

| Streak day | Daily claim | Streak bonus | **Total** |
|---|---|---|---|
| 1–6 | 10 | 0 | **10** |
| 7 | 10 | 10 | **20** |
| 14, 21, 28 | 10 | 20 | **30** |

- Resets at **00:00 UTC** (= 07:00 WIB)
- Signup bonus: 100 Merits (200 with a referral code)
- Merits are tied to your wallet address, across chains

---

## Requirements

| | |
|---|---|
| Python | 3.9 or newer |
| Package | `eth-account` (installed above) |
| Wallet | Any EVM wallet that's registered on Blockscout Merits |

---

## About your private key — read this

Logging in requires a **wallet signature**, and signing requires your private key. There's no way around that — it's how SIWE (Sign-In With Ethereum) works.

**But you only need it once.** The login produces a JWT that lasts **~365 days**.

So:

```bash
python3 login_interactive.py
```

This prompts for your key **in your own terminal**:
- Not echoed to the screen
- Not saved to shell history
- Not logged anywhere
- Not written to disk

Only `tokens.json` (the JWT) gets saved. After that, your private key isn't needed for a year.

> ### ⚠️ Security rules
>
> 1. **Never send your private key to anyone.** Not to an AI, not in a chat, not in a gist. Anyone with your key owns your wallet.
> 2. **If it's your main wallet, don't put the key on a server at all.** Use `login_interactive.py` locally, or use a dedicated burner wallet for airdrop farming.
> 3. `tokens.json` is account access too — keep it private (the tool sets `chmod 600` for you).
> 4. Both `wallets.txt` and `tokens.json` are in `.gitignore`. Don't remove them from it.

### Two ways to log in

| Mode | Command | Key on disk? |
|---|---|---|
| **Interactive** (recommended) | `python3 login_interactive.py` | ❌ Never |
| Non-interactive | `python3 claim.py --login --key 0x...` | ❌ Not saved |
| Batch / scripted | Put keys in `wallets.txt`, run `python3 claim.py --login` | ⚠️ Yes, in `wallets.txt` |

---

## Commands

| Command | What it does |
|---|---|
| `python3 login_interactive.py` | Sign in once. Private key never touches disk. |
| `python3 claim.py --login` | Sign in using keys from `wallets.txt`. |
| `python3 claim.py --login --key 0x...` | Sign in with one key, without saving it. |
| `python3 claim.py --status` | Show balance, streak, and whether you can claim. |
| `python3 claim.py --dry-run` | Check only — doesn't claim. |
| `python3 claim.py` | Claim for every stored wallet. |
| `python3 claim.py --only 2` | Claim for wallet #2 only. |
| `python3 claim.py --quiet` | Summary only (used by cron). |

---

## Multiple wallets

**Option A — interactive, one at a time:**

```bash
python3 login_interactive.py    # wallet 1
python3 login_interactive.py    # wallet 2
python3 claim.py                # claims all of them
```

**Option B — batch:**

```bash
cp wallets.txt.example wallets.txt
nano wallets.txt                # one private key per line
chmod 600 wallets.txt
python3 claim.py --login        # logs in all of them
rm wallets.txt                  # optional: keys no longer needed
```

Each token is stored separately, so `claim.py` handles them all in one run with a 3-second gap between accounts.

---

## Scheduling

### Linux cron

```cron
# 00:10 UTC = 07:10 WIB — just after the daily reset
10 0 * * * cd /path/to/blockscout-merits-autoclaim && ./blockscout_merits_daily.sh
```

### Hermes Agent

```python
cronjob(action="create", name="blockscout-merits-daily", schedule="10 7 * * *",
        script="blockscout_merits_daily.sh", no_agent=True, deliver="origin")
```

The wrapper stays **silent** unless a claim actually happened or something failed — no daily spam.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Tidak ada token valid` | Not logged in yet | Run `login_interactive.py` |
| `token expired/invalid — jalankan --login lagi` | JWT older than ~1 year | Log in again |
| `login gagal` | Wrong private key format | Must be `0x` + 64 hex chars |
| `nonce gagal` | Network issue or rate limit | Wait a minute, retry |
| `sudah claim hari ini` | Already claimed today | Not an error — normal |
| `command not found: pip` | pip missing | `python3 -m pip install eth-account` |

Need to reset? Delete `tokens.json` and log in again.

---

## How it works (verified 2026-10-14)

Base URL: `https://merits.blockscout.com/api/v1`

```
GET  /auth/nonce?blockscout_login_address=<addr>&blockscout_login_chain_id=1
     -> {"nonce": "...", "merits_login_nonce": "..."}

# Sign this exact SIWE message:
eth.blockscout.com wants you to sign in with your Ethereum account:
<address>

Sign in/up to Blockscout Account V2 & Blockscout Merits program. Merits nonce: <merits_login_nonce>.

URI: https://eth.blockscout.com
Version: 1
Chain ID: 1
Nonce: <nonce>
Issued At: <ISO8601 Z>
Expiration Time: <ISO8601 Z, +1y>

POST /auth/login  {"nonce","message","signature"}  -> {"token": "<JWT>"}
GET  /user/balances     (Bearer)  -> {"total":"100", ...}
GET  /user/daily/check  (Bearer)  -> {"available":bool,"total_reward":"10","streak":"N", ...}
POST /user/daily/claim  (Bearer, empty body) -> {"total_reward":"10","streak":"N"}
```

### Gotchas if you're building your own

- Send `origin: https://eth.blockscout.com` and `referer: https://eth.blockscout.com/` — it's a same-site CORS endpoint.
- The nonce is **single-use**. Fetch a fresh one per attempt.
- `merits_login_nonce` and `nonce` are **different values** and both go in the message (one in the body text, one on the `Nonce:` line). Swapping them breaks auth.
- The signature needs the `0x` prefix; `eth_account`'s `.signature.hex()` sometimes omits it.
- Claiming is idempotent per day — a second call returns `available: false`, which is success, not an error.
- Don't retry 4xx responses (except 429).
- `login.blockscout.com` is Auth0 for the human dashboard. The Merits API is separate and wallet-based — don't automate the Auth0 path.

---

## Files

| File | Purpose |
|---|---|
| `claim.py` | Main tool — login, status, check, claim. |
| `login_interactive.py` | Sign in once without exposing your key. |
| `blockscout_merits_daily.sh` | Cron wrapper — silent unless there's news. |
| `wallets.txt.example` | Template for batch login. |
| `tokens.json.example` | Shows where tokens are stored. |

Generated at runtime (both gitignored): `tokens.json`, `wallets.txt`, `state.json`, `claim.log`.

---

## Disclaimer

This automates **your own** account's daily claim. Blockscout's Merits program is designed around daily manual visits, so automated claiming may conflict with their Terms of Service. You use it at your own risk.

Merits have no material value and may never convert to anything.

---

## License

MIT — see [LICENSE](LICENSE).
