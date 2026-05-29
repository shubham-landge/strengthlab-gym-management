# StrengthLab Local

Python/Flask gym management dashboard for local network deployment.

## Features

- Admin dashboard for members, trainers, equipment, attendance, payments, reports, and announcements.
- Member dashboard with subscription status, BMI, trainer assignment, payment history, workout plan, and diet plan.
- Rule-based plan generation when adding a member, using health declaration, goals, body stats, and premium flag.
- WhatsApp-ready notification links for broadcasts, payment reminders, payment received messages, and progress updates.
- Diet plan PDF download for sharing with members.
- SQLite database seeded automatically on first run.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` on the host machine.

## Demo Logins

- Admin: `admin` / `admin123`
- Owner: `owner` / `owner123`
- Accountant: `accountant` / `accountant123`
- Trainer: use trainer mobile number as Login ID. Default password is the last 4 digits of the mobile number.
- Member: use member mobile number as Login ID. Default password is the last 4 digits of the mobile number.

Admins can manage the full system. Trainers can view their assigned members and attendance. Members are redirected to their own dashboard.

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

## OpenAI Plan Generation

The app can generate workout and diet plans with the OpenAI API. Set your API key before starting the server:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-5.2"
python app.py
```

If `OPENAI_API_KEY` is not set, the app automatically uses the built-in local plan generator.
