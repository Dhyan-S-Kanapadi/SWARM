# SWARM.AI

SWARM.AI is a local-business app factory. A user enters a plain-language business problem, and SWARM coordinates agents that analyze requirements, design the app, build a runnable project, and summarize the result.

## Planned Stack

- Backend: Python FastAPI
- Agent orchestration: LangGraph StateGraph
- LLM provider: Groq
- Frontend: React and Vite
- Generated apps: React, Express, and a local JSON database

## Repository Layout

```text
backend/
  __init__.py
  main.py
  state.py
frontend/
  index.html
  package.json
  src/
    App.jsx
    main.jsx
```

## Current Status

This repository currently contains the initial project skeleton. Backend API endpoints, agent orchestration, generated app creation, preview support, and validation are added in later milestones.
