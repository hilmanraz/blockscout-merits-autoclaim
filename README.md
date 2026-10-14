# Blockscout Merits — Auto Daily Check-In

Automate the [Blockscout Merits](https://merits.blockscout.com/) daily claim (**+10 Merits/day**, resets **00:00 UTC**) without a browser.

Uses the private REST API + **SIWE (EIP-4361)** wallet signature. Pure Python — no browser, no Playwright, no headless Chrome.

```
nonce → sign SIWE message → JWT (~365 days) → daily check → daily claim
```

---

## Why this exists

Blockscout Merits requires a manual daily visit to keep your streak. This tool claims it for you on a schedule, across multiple wallets, and only notifies you when something actually happened.

**Reward schedule** (from Blockscout docs):

| Streak day | Daily claim | Streak bonus | Total |
|---|---|---|---|
| 1–6 | 10 | 0 | 10 |
| 7 | 10 | 10 | 20 |
| 14, 21, 28 | 10 | 20 | 30 |

Signup bonus: 100 Merits (200 with a referral code). Merits are chain-agnostic and tied to your EOA.

---

## Key handling — private key is needed **once**, not daily

SIWE requires a wallet signature, and signing requires the private key. **But the resulting JWT is valid ~365 days.**

Two modes:

| Mode | How it works | Key on disk? |
|---|---|---|
| **Token mode** (recommended) | Sign once, store JWT in `tokens.json` | No — key can be deleted after login |
| Key mode | Re-sign on every run | Yes, in `wallets.txt` |

### Safest path — sign once, key never leaves your machine

```bash
python3 login_interactive.py
```

- Prompts for your private key **in your own terminal**
- Input is **not echoed**, **not written to shell history**, **not logged**, **not saved to disk**
- Only `tokens.json` (the JWT) is written, chmod 600
- After this, the private key is not needed again for ~1 year

> ⚠️ **Never send your private key to anyone** — not to an AI agent, not in a chat, not in a pastebin. If a wallet is your main wallet, do not put its key on a server at all. Use `login_interactive.py`, or use a dedicated burner wallet for farming.

---

## Install

```bash
git clone https://github.com/<you>/blockscout-merits-autoclaim.git
cd blockscout-merits-autoclaim
pip install eth-account
```

Requires Python 3.9+.

---

## Usage

### 1. Login once (get a token)

Interactive (recommended — key never touches disk):

```bash
python3 login_interactive.py
```

Or non-interactive:

```bash
python3 claim.py --login --key 0xYOUR_PRIVATE_KEY     # key not written to disk
python3 claim.py --login                              # reads wallets.txt
```

### 2. Verify

```bash
python3 claim.py --status      # balance / streak / claimable per wallet
python3 claim.py --dry-run     # check only, does not claim
```

### 3. Claim

```bash
python3 claim.py               # live claim via stored token
python3 claim.py --only 1      # single wallet (1-based index)
python3 claim.py --quiet       # summary only (for cron)
```

### Multiple wallets

Either run `--login --key` for each wallet, or put one key per line in `wallets.txt` and run `--login`.

---

## Scheduling

### Linux cron

```cron
# 07:10 WIB (00:10 UTC) — shortly after the 00:00 UTC reset
10 0 * * * cd /path/to/blockscout-merits-autoclaim && ./blockscout_merits_daily.sh
```

### Hermes Agent

```python
cronjob(action="create", name="blockscout-merits-daily", schedule="10 7 * * *",
        script="blockscout_merits_daily.sh", no_agent=True, deliver="origin")
```

The wrapper is **silent** unless a claim actually succeeded or a failure occurred — no daily spam.

---

## Verified API flow

Base: `https://merits.blockscout.com/api/v1`

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

POST /auth/login  {"nonce","message","signature"}  -> {"created":bool,"token":"<JWT>"}
GET  /user/balances     (Bearer)  -> {"total":"100","staked":"0","unstaked":"100", ...}
GET  /user/daily/check  (Bearer)  -> {"available":bool,"daily_reward":"10","streak_reward":"0",
                                      "total_reward":"10","date":"YYYY-MM-DD","reset_at":"...","streak":"N"}
POST /user/daily/claim  (Bearer, empty body) -> {"daily_reward":"10","streak_reward":"0",
                                                 "total_reward":"10","streak":"N"}
```

Verified working as of **2026-10-14**.

---

## Pitfalls

- **Headers matter.** Send `origin: https://eth.blockscout.com`, `referer: https://eth.blockscout.com/`, and a real desktop Chrome user-agent. It's a same-site CORS endpoint.
- **Nonce is single-use.** Fetch a fresh one per attempt.
- **`merits_login_nonce` ≠ `nonce`.** Both appear in the message (one in the body text, one on the `Nonce:` line). Swapping them fails auth.
- **Signature needs the `0x` prefix.** `eth_account`'s `.signature.hex()` may omit it.
- **Claim is idempotent per day.** Re-running returns `available: false` — that's success, not an error.
- **Don't retry 4xx** (except 429).
- **`login.blockscout.com` is Auth0** (OIDC) for the human dashboard. The Merits program API is separate and wallet-based — don't try to automate the Auth0 path.

---

## Files

| File | Purpose |
|---|---|
| `claim.py` | Main tool — login, status, check, claim. Token + key modes. |
| `login_interactive.py` | Sign once without exposing the key. |
| `blockscout_merits_daily.sh` | Cron wrapper — silent unless there's news. |
| `wallets.txt` | Optional private keys (one per line). **Gitignored.** |
| `tokens.json` | Stored JWTs. **Gitignored.** |

---

## Disclaimer

This automates **your own** account's daily claim. Blockscout's Merits program is designed around daily manual visits; automated claiming may conflict with their Terms of Service. Use at your own risk, and understand that you are responsible for how you use it.

Merits have no material value and may or may not convert to anything in the future.

---

## License

MIT — see [LICENSE](LICENSE).
