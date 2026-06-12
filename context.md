# SWARM.AI Project Context

## Project

SWARM.AI is an AI app generator for local businesses. The goal is: a local shop owner types a plain-language problem, and SWARM generates a runnable business management app with frontend, backend, local database, seed data, dashboard, validation, and preview links.

## Current Direction

We originally tried to integrate Trae MCP, but later the hackathon requirement changed and Trae was no longer mandatory. So the project was upgraded to work independently without Trae.

Current flow:

```text
User prompt
  -> Analyst agent
  -> Architect agent
  -> SWARM Builder agent
  -> Pitcher agent
  -> Generated runnable app
```

## Current Tech

Main SWARM app:

- Backend: FastAPI / Python
- Frontend: React + Vite
- LLM: Groq API for Analyst, Architect, Pitcher
- Builder: internal deterministic code generator
- Output apps: React + Express + local JSON persistence

Generated apps include:

- React frontend
- Express backend
- Local JSON database
- CRUD APIs
- Dashboard metrics
- Seed data
- Tests
- README
- Preview launch support

## Important Pivot

The Builder agent does not use Trae anymore. It generates the app internally.

Groq is used for:

- Analyst: product requirements
- Architect: app architecture
- Pitcher: pitch summary

Builder is currently deterministic/template-driven for reliability. It uses the prompt + requirements + architecture to generate runnable app files.

## Key Problems Fixed

1. Groq 429 rate limits
   Reduced token usage and added fallback behavior.

2. Groq malformed JSON
   Added JSON repair retry before fallback.

3. Groq 413 request too large
   Added request-size fitting and compact Architect input.

4. Builder always seeming like bakery output
   Fixed domain detection so user prompt is the source of truth. Added `saloon` as a salon keyword.

5. Stale preview showing old app
   Identified that old generated app servers on ports `3001/6200` can keep running. Cleared stale preview processes and relaunched latest generated app.

## Current Builder Behavior

The builder now detects domains like:

- bakery
- salon / saloon / beauty / barber / makeup
- clinic
- fitness studio
- tuition center
- generic local business

For salon/saloon prompts, it now generates:

- salon business type
- appointment queue
- hair/beauty service records
- staff schedules
- payment status
- reminders/follow-ups
- revenue metrics
- English/Hindi/Kannada labels

Verified example prompt:

```text
Build a saloon management app with customer profiles, staff schedules, hair and beauty service bookings, payment status, reminders, daily appointment queue, revenue dashboard, and English/Hindi/Kannada labels.
```

Generated:

- app name: `build-saloon-management`
- business type: `salon`
- queue: `appointment queue`
- validation: passed
- quality: `99/100`

## Current Live Local Links

If servers are running:

```text
SWARM frontend:
http://127.0.0.1:5173

SWARM backend health:
http://127.0.0.1:8000/health

Generated app preview:
http://127.0.0.1:6200

Generated app API:
http://127.0.0.1:3001
```

## How To Run Locally

From project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
$env:VITE_API_BASE_URL='http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1 --port 5173
```

## Environment

`.env` should contain:

```env
GROQ_API_KEY=your_groq_key
```

Optional config:

```env
GROQ_MODEL=llama-3.1-8b-instant
GROQ_REQUEST_TOKEN_BUDGET=5600
GROQ_ANALYST_MAX_TOKENS=2200
GROQ_ARCHITECT_MAX_TOKENS=2800
GROQ_ARCHITECT_REPAIR_MAX_TOKENS=3200
GROQ_PITCHER_MAX_TOKENS=900
```

## Latest GitHub Status

Repo:

```text
https://github.com/Dhyan-S-Kanapadi/SWARM.AI
```

Latest commit before this context file:

```text
b681ad6 Prioritize prompt domain in builder
```

GitHub was up to date before adding this file.

## What Has Been Completed

- Backend workflow works.
- Frontend SWARM UI works.
- Groq integration works with retries/fallbacks.
- Internal builder creates runnable generated apps.
- Generated app preview launch works.
- Generated app validation works.
- Generated app download works.
- Domain-specific generation now works for salon/saloon.
- Code has been pushed to GitHub.

## Current Limitation

The builder is reliable but still template-driven. It creates strong local-business management apps, but it is not yet a fully free-form coding agent like Bolt/Lovable. That was intentional so the hackathon demo remains stable and generated apps pass validation.

## Best Current Pitch

SWARM.AI is a local-business app factory. A bakery, salon, clinic, tuition center, or small shop owner types their workflow problem, and SWARM generates a working management app with dashboard, CRUD, local-language UX, seed data, tests, and live preview links.
