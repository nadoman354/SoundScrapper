# Agent Rules

## Reading Order
1. Docs/CurrentTask.md
2. Docs/ErrorLog.md
3. Docs/DecisionLog.md
4. Docs/Architecture.md
5. README.md

## Verification Rules
- Do not claim a feature works without running the relevant command.
- After code changes, run static analysis first.
- If Unity Editor is open, do not run Unity batchmode.
- Suggest Unity batchmode compilation only when interfaces, asmdef files, MonoBehaviours, ScriptableObjects, or prefabs change.
- If a command cannot be run, clearly report why.
- Keep changes small and task-focused.
- Do not rewrite architecture documents unless explicitly asked.

## Project Goal
Build a local web app for searching and evaluating game-ready SFX/BGM samples from legal free sources such as Freesound.

## Initial Stack
- Backend: Python FastAPI
- Frontend: HTML/CSS/Vanilla JS first
- DB: SQLite
- Audio analysis: later phase

