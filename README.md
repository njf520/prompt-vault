\# ⚑ PromptVault



> \*\*Version control for LLM prompts.\*\* Track changes, compare versions, and manage your prompt library with the discipline you'd apply to any production codebase.



!\[Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat\&logo=python\&logoColor=white)

!\[FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat\&logo=fastapi\&logoColor=white)

!\[License](https://img.shields.io/badge/License-MIT-green?style=flat)



\---



\## The Problem



Prompt engineering is real engineering — but most teams treat prompts like sticky notes.



A prompt gets tweaked in a Slack thread. Someone edits it directly in the codebase with no comment. A model upgrade changes behavior and no one knows which version of the prompt was "the good one." When something breaks in production, there's no audit trail.



\*\*Teams shipping AI features need the same discipline for prompts that they have for code.\*\*



\---



\## What PromptVault Does



PromptVault is a lightweight REST service + web UI that brings version control semantics to LLM prompts:



\- \*\*Commit new versions\*\* of a prompt with notes explaining \*why\* it changed

\- \*\*Diff any two versions\*\* side-by-side to see exactly what was modified

\- \*\*Tag prompts\*\* by use case, model, or lifecycle stage (e.g. `production`, `experiment`, `deprecated`)

\- \*\*Pin a model target\*\* to each version so you know which prompt was tuned for which model

\- \*\*Search and filter\*\* your entire prompt library by name, tag, or content

\- \*\*Hash every version\*\* for reproducibility — pin a `hash` in your app code to ensure you always load the exact prompt you tested



\---



\## Architecture



!\[PromptVault Architecture](static/architecture.svg)



\*\*Design decision:\*\* The storage layer is intentionally a single JSON file for v1. This makes the tool portable (zero DB setup), easy to inspect, and trivial to commit into a git repo alongside your codebase — so you get \*two\* layers of version control if you want them.



\---



\## Quick Start



\*\*1. Clone and install\*\*



```bash

git clone https://github.com/njf520/prompt-vault.git

cd prompt-vault

pip install -r requirements.txt

```



\*\*2. Run the server\*\*



```bash

uvicorn app:app --reload --port 8000

```



\*\*3. Open the UI\*\*



```

http://localhost:8000

```



Click \*\*"⚡ Load Demo Data"\*\* to seed the vault with example prompts and explore the interface.



\---



\## API Reference



All endpoints return JSON. Base URL: `http://localhost:8000/api`



| Method | Endpoint | Description |

|--------|----------|-------------|

| `GET` | `/prompts` | List all prompts. Filter by `?tag=` or `?search=` |

| `POST` | `/prompts` | Create a new prompt (v1) |

| `GET` | `/prompts/{name}` | Get latest version. Pin with `?version=2` |

| `PUT` | `/prompts/{name}` | Commit a new version |

| `GET` | `/prompts/{name}/history` | Full version history |

| `GET` | `/prompts/{name}/diff?v1=1\&v2=2` | Unified diff between versions |

| `DELETE` | `/prompts/{name}` | Delete prompt and all versions |

| `GET` | `/tags` | All unique tags across the library |



\*\*Example: Create a prompt\*\*

```bash

curl -X POST http://localhost:8000/api/prompts \\

&#x20; -H "Content-Type: application/json" \\

&#x20; -d '{

&#x20;   "name": "support-greeting",

&#x20;   "content": "You are a helpful customer support agent.",

&#x20;   "tags": \["support", "v1"],

&#x20;   "model\_target": "gpt-4o",

&#x20;   "notes": "Initial draft"

&#x20; }'

```



\*\*Example: Fetch a specific version by number (for reproducibility)\*\*

```bash

curl "http://localhost:8000/api/prompts/support-greeting?version=2"

```



\---



\## Usage Patterns



\### Pattern 1: Developer integration

Pin prompt versions in application code to prevent silent regressions:



```python

import httpx



def get\_prompt(name: str, version: int = None) -> str:

&#x20;   url = f"http://localhost:8000/api/prompts/{name}"

&#x20;   if version:

&#x20;       url += f"?version={version}"

&#x20;   resp = httpx.get(url)

&#x20;   return resp.json()\["content"]



\# Pinned to v3 — won't drift if someone updates the library

system\_prompt = get\_prompt("support-greeting", version=3)

```



\### Pattern 2: Prompt A/B testing workflow

Tag experimental prompts and compare performance before promoting:



```

v1: tags=\["baseline"]          → deployed to 100% of users

v2: tags=\["experiment"]        → shadow-tested on 10% of traffic

v3: tags=\["production"]        → promoted after eval results

```



\### Pattern 3: Model migration

When upgrading from GPT-3.5 → GPT-4o, create new versions tagged for the target model without losing the old ones.



\---



\## What I'd Do Differently at Scale



This is a PoC. Here's what a production version would need:



| Concern | v1 (this repo) | Production approach |

|---------|----------------|---------------------|

| \*\*Storage\*\* | JSON flat file | PostgreSQL with full-text search |

| \*\*Auth\*\* | None | OAuth2 / API key per team |

| \*\*Environments\*\* | None | `dev / staging / prod` promotion gates |

| \*\*Evaluation\*\* | None | Link prompt versions to evals/test suites |

| \*\*Access control\*\* | None | Role-based: viewer, editor, publisher |

| \*\*Audit log\*\* | Version history | Immutable append-only log with user attribution |

| \*\*CI/CD integration\*\* | None | GitHub Action to lint/test prompts on PR |

| \*\*Rollback\*\* | Manual API call | One-click rollback in UI with deployment record |



The most important missing piece for enterprise use is \*\*evaluation linkage\*\* — the ability to tie a prompt version to a set of test cases and their pass/fail results. Without that, "version 4 is better" is just a vibe.



\---



\## Project Structure



```

prompt-vault/

├── app.py              # FastAPI application + all API routes

├── requirements.txt    # Python dependencies

├── prompts\_db/

│   └── vault.json      # Prompt storage (auto-created on first run)

└── static/

&#x20;   ├── index.html      # Single-file web UI (no build step)

&#x20;   └── architecture.svg

```



\---



\## Why This Matters for AI Teams



Prompt management is the unglamorous work that determines whether an AI product is reliable in production. The failure modes are subtle:



\- A well-intentioned edit to a shared prompt silently degrades a downstream feature

\- A model version bump changes behavior and there's no baseline to diff against

\- The "prompt that worked in demos" can't be reconstructed because it was never tracked



PromptVault treats prompts as \*\*first-class engineering artifacts\*\* — versioned, auditable, and shareable — because that's what they are.



\---



\## Tech Stack



\- \*\*Backend:\*\* Python 3.11, FastAPI, Pydantic v2

\- \*\*Storage:\*\* JSON (file-based, zero dependencies)

\- \*\*Frontend:\*\* Vanilla JS, HTML/CSS (no build step, no framework)

\- \*\*Diff engine:\*\* Python stdlib `difflib` (unified diff format)



\---



\## License



MIT — use it, fork it, build on it.

