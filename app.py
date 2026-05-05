"""
PromptVault - Prompt Version Control Tool
==========================================
A lightweight REST API that brings version control to LLM prompts.

Why FastAPI?
- It's the most popular Python framework for building APIs in AI/ML teams
- It auto-generates interactive docs at /docs (great for demos)
- It validates incoming data automatically using Pydantic models
- It's fast to write — ideal for a PoC

Why a JSON file instead of a database?
- Zero setup: anyone can clone and run this in two commands
- Easy to inspect: open vault.json in any text editor and read it directly
- The right tradeoff for a PoC — the README documents what we'd use in production
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel  # Pydantic validates incoming request data automatically
from typing import Optional
import json
import os
import hashlib                  # Used to generate a short fingerprint (hash) for each prompt version
from datetime import datetime, timezone
import difflib                  # Python's built-in diff library — same algorithm Git uses

# ── App Setup ─────────────────────────────────────────────────────────────────
# This creates the FastAPI application. Title and description appear in the
# auto-generated docs at http://localhost:8000/docs
app = FastAPI(
    title="PromptVault",
    description="Version control for LLM prompts",
    version="1.0.0"
)

# ── Storage Setup ─────────────────────────────────────────────────────────────
# All prompts are stored in a single JSON file.
# Structure: { "prompts": { "prompt-name": [ ...versions ] } }
DB_PATH = "prompts_db/vault.json"

def load_db() -> dict:
    """Load the prompt database from disk. Returns empty structure if file doesn't exist yet."""
    if not os.path.exists(DB_PATH):
        return {"prompts": {}}
    with open(DB_PATH) as f:
        return json.load(f)

def save_db(db: dict):
    """Save the prompt database back to disk. Creates the folder if it doesn't exist."""
    os.makedirs("prompts_db", exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)

def make_id(text: str) -> str:
    """
    Generate a short 8-character hash fingerprint from prompt content.
    This lets developers pin an exact version of a prompt in their application code.
    Same concept as a Git commit hash.
    """
    return hashlib.sha1(text.encode()).hexdigest()[:8]


# ── Data Models ───────────────────────────────────────────────────────────────
# Pydantic models define the shape of data we expect in API requests.
# FastAPI will automatically return a 422 error if required fields are missing.

class PromptCreate(BaseModel):
    """Shape of data required to create a new prompt (v1)."""
    name: str           # Unique identifier, e.g. "customer-support-greeting"
    content: str        # The actual prompt text
    tags: list[str] = []        # Optional tags, e.g. ["production", "support"]
    model_target: str = ""      # Which LLM this was tuned for, e.g. "gpt-4o"
    notes: str          # Required — commit message explaining why this prompt exists

class PromptUpdate(BaseModel):
    """Shape of data required to commit a new version of an existing prompt."""
    content: str
    tags: list[str] = []
    model_target: str = ""
    notes: str          # Required — must explain what changed and why


# ── API Routes ────────────────────────────────────────────────────────────────
# Each route is a URL endpoint. FastAPI maps HTTP methods (GET, POST, PUT, DELETE)
# to these functions automatically.

@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the web UI. When you open http://localhost:8000, this runs first."""
    return FileResponse("static/index.html")


@app.get("/api/prompts")
def list_prompts(tag: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    """
    List all prompts, showing only the latest version of each.
    Supports optional filtering:
      ?tag=production     → only prompts tagged "production"
      ?search=customer    → only prompts with "customer" in name or content
    """
    db = load_db()
    results = []
    for name, versions in db["prompts"].items():
        latest = versions[-1]   # Always show the most recent version in the list
        if tag and tag not in latest["tags"]:
            continue
        if search and search.lower() not in latest["content"].lower() and search.lower() not in name.lower():
            continue
        results.append({
            "name": name,
            "version": len(versions),
            "latest": latest,
            "version_count": len(versions),
        })
    # Sort by most recently saved first
    return sorted(results, key=lambda x: x["latest"]["created_at"], reverse=True)


@app.post("/api/prompts", status_code=201)
def create_prompt(prompt: PromptCreate):
    """
    Create a new prompt at version 1.
    Returns a 400 error if a prompt with this name already exists
    (use PUT to add a new version instead).
    """
    db = load_db()
    if prompt.name in db["prompts"]:
        raise HTTPException(400, f"Prompt '{prompt.name}' already exists. Use PUT to update.")
    if not prompt.notes.strip():
        raise HTTPException(400, "Commit notes are required.")
    entry = {
        "version": 1,
        "content": prompt.content,
        "tags": prompt.tags,
        "model_target": prompt.model_target,
        "notes": prompt.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),  # UTC timestamp for consistency
        "hash": make_id(prompt.content),                        # Short fingerprint for pinning
    }
    db["prompts"][prompt.name] = [entry]    # Start version history as a list with one item
    save_db(db)
    return {"name": prompt.name, "version": 1, "hash": entry["hash"]}


@app.put("/api/prompts/{name}")
def update_prompt(name: str, prompt: PromptUpdate):
    """
    Commit a new version of an existing prompt.
    Checks ALL fields for changes — not just content.
    This means updating only the model target or tags also triggers a new version.
    Returns a 400 error if nothing actually changed (prevents empty commits).
    """
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    if not prompt.notes.strip():
        raise HTTPException(400, "Commit notes are required.")
    versions = db["prompts"][name]
    last = versions[-1]     # Compare against the most recent version

    # Check all four fields — if nothing changed, reject the commit
    if (last["content"] == prompt.content and
        last.get("model_target") == prompt.model_target and
        last.get("tags") == prompt.tags and
        last.get("notes") == prompt.notes):
        raise HTTPException(400, "No changes detected. Nothing was modified.")

    new_version = len(versions) + 1
    entry = {
        "version": new_version,
        "content": prompt.content,
        "tags": prompt.tags,
        "model_target": prompt.model_target,
        "notes": prompt.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hash": make_id(prompt.content),
    }
    db["prompts"][name].append(entry)   # Append to history — we never overwrite old versions
    save_db(db)
    return {"name": name, "version": new_version, "hash": entry["hash"]}


@app.get("/api/prompts/{name}")
def get_prompt(name: str, version: Optional[int] = Query(None)):
    """
    Get a prompt's content.
    Without ?version=N, returns the latest version.
    With ?version=2, returns that exact version — useful for pinning in application code.
    """
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    versions = db["prompts"][name]
    if version:
        if version < 1 or version > len(versions):
            raise HTTPException(400, f"Version {version} out of range (1-{len(versions)}).")
        return {"name": name, **versions[version - 1]}
    return {"name": name, "version_count": len(versions), **versions[-1]}


@app.get("/api/prompts/{name}/history")
def get_history(name: str):
    """Return the full version history of a prompt — all versions, oldest to newest."""
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    return {"name": name, "versions": db["prompts"][name]}


@app.get("/api/prompts/{name}/diff")
def diff_versions(name: str, v1: int = Query(...), v2: int = Query(...)):
    """
    Compare two versions of a prompt using unified diff format.
    This is the same diff algorithm used by Git.
    The UI renders additions in green and deletions in red.
    Example: /api/prompts/my-prompt/diff?v1=1&v2=2
    """
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    versions = db["prompts"][name]
    max_v = len(versions)
    if not (1 <= v1 <= max_v and 1 <= v2 <= max_v):
        raise HTTPException(400, f"Versions must be between 1 and {max_v}.")
    # Split content into lines for line-by-line comparison
    a = versions[v1 - 1]["content"].splitlines(keepends=True)
    b = versions[v2 - 1]["content"].splitlines(keepends=True)
    diff = list(difflib.unified_diff(a, b, fromfile=f"v{v1}", tofile=f"v{v2}"))
    return {"name": name, "v1": v1, "v2": v2, "diff": "".join(diff)}


@app.delete("/api/prompts/{name}")
def delete_prompt(name: str):
    """Delete a prompt and its entire version history. This is permanent."""
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    del db["prompts"][name]
    save_db(db)
    return {"deleted": name}


@app.get("/api/tags")
def list_tags():
    """Return all unique tags used across the entire prompt library, sorted alphabetically."""
    db = load_db()
    tags = set()    # Using a set automatically removes duplicates
    for versions in db["prompts"].values():
        for v in versions:
            tags.update(v.get("tags", []))
    return sorted(tags)


# ── Demo Seed Data ────────────────────────────────────────────────────────────
@app.post("/api/seed")
def seed_demo():
    """
    Populate the vault with realistic example prompts for demos and testing.
    Each example has multiple versions to demonstrate the diff and history features.
    Skips any prompt that already exists — safe to call multiple times.
    """
    demos = [
        {
            "name": "customer-support-greeting",
            "versions": [
                ("You are a helpful customer support agent. Answer questions politely.", ["support", "v1"], "gpt-4o", "Initial draft"),
                ("You are a friendly, empathetic customer support specialist at Acme Corp. Always greet the user by name if provided. Answer questions clearly and offer to escalate to a human if unresolved.", ["support", "refined"], "gpt-4o", "Added empathy + escalation path"),
            ]
        },
        {
            "name": "code-review-assistant",
            "versions": [
                ("Review this code and suggest improvements.", ["engineering"], "claude-sonnet-4-20250514", "MVP"),
                ("You are a senior software engineer conducting a code review. Evaluate the code for: (1) correctness, (2) readability, (3) performance, (4) security. Format your response with headers for each category. Be specific and cite line numbers.", ["engineering", "structured"], "claude-sonnet-4-20250514", "Structured output format"),
                ("You are a senior software engineer. Review the provided code across four dimensions: correctness, readability, performance, and security. Use markdown headers. Cite line numbers. End with a 'Priority Fixes' section listing the top 3 most critical issues.", ["engineering", "structured", "production"], "claude-sonnet-4-20250514", "Added priority fixes section — better for triage"),
            ]
        },
        {
            "name": "sql-query-generator",
            "versions": [
                ("Convert the user's natural language question into a SQL query.", ["data", "sql"], "gpt-4o", "First pass"),
                ("Convert the user's natural language question into a valid PostgreSQL query. Return ONLY the SQL — no explanation. Assume the schema is provided in the system context.", ["data", "sql", "postgres"], "gpt-4o", "Scoped to Postgres, clean output"),
            ]
        },
    ]
    db = load_db()
    for demo in demos:
        name = demo["name"]
        if name in db["prompts"]:
            continue    # Don't overwrite existing prompts
        db["prompts"][name] = []
        for i, (content, tags, model, notes) in enumerate(demo["versions"], 1):
            db["prompts"][name].append({
                "version": i,
                "content": content,
                "tags": tags,
                "model_target": model,
                "notes": notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "hash": make_id(content),
            })
    save_db(db)
    return {"seeded": [d["name"] for d in demos]}