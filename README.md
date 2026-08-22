# StrengthLab Local

Python/Flask gym management dashboard for local network deployment.

## Prerequisites

- Python `3.10+` (recommended `3.11`)
- Git `2.40+`

## Features

- Admin dashboard for members, trainers, equipment, attendance, payments, reports, and announcements.
- Member dashboard with subscription status, BMI, trainer assignment, payment history, workout plan, and diet plan.
- Rule-based plan generation when adding a member, using health declaration, goals, body stats, and premium flag.
- WhatsApp-ready notification links for broadcasts, payment reminders, payment received messages, and progress updates.
- Diet plan PDF download for sharing with members.
- SQLite database seeded automatically on first run.

## Run Locally

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

macOS / Linux:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python app.py
```

Open `http://localhost:5000` on the host machine.

> **macOS:** port `5000` is used by the AirPlay Receiver. Either turn it off in
> *System Settings → General → AirDrop & Handoff → AirPlay Receiver*, or start the
> app on another port with `PORT=5001 python app.py`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers every page route, the PDF/Excel exports, login and role routing,
CSRF enforcement, and the finance calculations. Tests run against a temporary
SQLite file and never touch `gym_manager.db`.

## Demo Logins

- Admin: `admin` / `admin123`
- Owner: `owner` / `owner123`
- Accountant: `accountant` / `accountant123`
- Trainer: use trainer mobile number as Login ID. Default password is the last 4 digits of the mobile number.
- Member: use member mobile number as Login ID. Default password is the last 4 digits of the mobile number.

On a freshly seeded database the sample accounts are `9999111222` / `1222` (member)
and `9999000111` / `0111` (trainer). There is no `trainer/trainer123` or
`member/member123` login: seeded trainer and member accounts are converted to
mobile-number login IDs on first run.

Admins can manage the full system. Trainers can view their assigned members and attendance. Members are redirected to their own dashboard.

Default mobile passwords must be changed on first login. Admin password resets also force the user to choose a new password on next login. A local forgot-password reset link flow is available from the login page.

If `python` opens the Microsoft Store instead of running Python, install Python from
python.org or create the venv with an existing interpreter path. On this machine,
this worked:

```powershell
& "$env:USERPROFILE\.platformio\python3\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

For other devices on the same Wi-Fi/LAN, open:

```text
http://<your-computer-ip>:5000
```

The app binds to `0.0.0.0` so LAN devices can access it if Windows Firewall allows Python on port `5000`.

## Security and Configuration

- **Session secret.** Set `SECRET_KEY` in the environment for any shared deployment.
  If it is not set, the app generates a random key on first run and stores it in
  `.secret_key` (gitignored) so sessions survive restarts.
- **CSRF.** Every form posts a per-session token; unverified posts are rejected with
  HTTP 400. Templates emit the token via `{{ csrf_token() }}`.
- **Cookies.** Session cookies are `HttpOnly` and `SameSite=Lax`. When serving over
  HTTPS, also set `SESSION_COOKIE_SECURE=1`.
- **Passwords.** Trainer/member default passwords are the last 4 digits of the mobile
  number and must be changed at first login.
- **Production.** `python app.py` runs Flask's development server. Serve with
  gunicorn instead: `gunicorn --bind=0.0.0.0:5000 app:app`.

Other environment settings:

```bash
GYM_DB_PATH=/path/to/gym_manager.db   # override the SQLite location
DISABLE_PAYMENT_AUTOMATION=1          # skip the hourly reminder worker
```

## WhatsApp Notes

This version uses WhatsApp click-to-send URLs and a notification queue. For automated background sending, connect the queue to WhatsApp Business Cloud API or Twilio using your approved business number and credentials.

## Payment Due Automation

The server checks for due payments every hour and queues WhatsApp reminders without duplicating the same reminder on the same day. It also queues renewal reminders one week before the membership end date and again on the renewal date. Admins can also run the scan manually from **Payments -> Run due reminders**.

Optional settings:

```powershell
$env:PAYMENT_REMINDER_DAYS="3"
$env:PAYMENT_REMINDER_INTERVAL_SECONDS="3600"
python app.py
```

## AI Plan Generation

The app can generate workout and diet plans with multiple AI providers. It tries providers, models, and keys in order. If one key is rate-limited or fails, the next key/model is used automatically. If all AI providers fail, the built-in local plan generator is used.

Workout and diet services are controlled separately per member:

- Workout Regular: built-in local plan generator.
- Workout Premium: admin-only AI-assisted workout draft, with local fallback.
- Diet None: no diet plan service.
- Diet Regular: built-in local diet generator.
- Diet Premium: admin-only AI-assisted diet draft, with local fallback.

Admins generate drafts from the member edit screen, choose clickable customization options, review the draft, then copy it into the final saved plan.

```powershell
$env:AI_PROVIDER_ORDER="openai,gemini"

# Single key or comma-separated multiple keys
$env:OPENAI_API_KEYS="openai_key_1,openai_key_2"
$env:OPENAI_MODELS="gpt-5.2,gpt-4o-mini"

# Gemini keys can use the Google AI Studio free tier where available
$env:GEMINI_API_KEYS="gemini_key_1,gemini_key_2"
$env:GEMINI_MODELS="gemini-2.5-flash,gemini-2.0-flash"

python app.py
```

Backward-compatible single-key settings also work:

```powershell
$env:OPENAI_API_KEY="your_openai_key"
$env:OPENAI_MODEL="gpt-5.2"
$env:GEMINI_API_KEY="your_gemini_key"
$env:GEMINI_MODEL="gemini-2.5-flash"
```
