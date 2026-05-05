"""
PromptVault - Prompt Version Control Tool
A lightweight versioning system for LLM prompts.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
import hashlib
from datetime import datetime, timezone
import difflib

app = FastAPI(title="PromptVault", description="Version control for LLM prompts", version="1.0.0")

# ── Storage ──────────────────────────────────────────────────────────────────
DB_PATH = "prompts_db/vault.json"

def load_db() -> dict:
    if not os.path.exists(DB_PATH):
        return {"prompts": {}}
    with open(DB_PATH) as f:
        return json.load(f)

def save_db(db: dict):
    os.makedirs("prompts_db", exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)

def make_id(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]

# ── Models ───────────────────────────────────────────────────────────────────
class PromptCreate(BaseModel):
    name: str
    content: str
    tags: list[str] = []
    model_target: str = ""
    notes: str

class PromptUpdate(BaseModel):
    content: str
    tags: list[str] = []
    model_target: str = ""
    notes: str

# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse("static/index.html")


@app.get("/api/prompts")
def list_prompts(tag: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    """List all prompts (latest version of each), with optional tag/search filter."""
    db = load_db()
    results = []
    for name, versions in db["prompts"].items():
        latest = versions[-1]
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
    return sorted(results, key=lambda x: x["latest"]["created_at"], reverse=True)


@app.post("/api/prompts", status_code=201)
def create_prompt(prompt: PromptCreate):
    """Create a new prompt (v1)."""
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hash": make_id(prompt.content),
    }
    db["prompts"][prompt.name] = [entry]
    save_db(db)
    return {"name": prompt.name, "version": 1, "hash": entry["hash"]}


@app.put("/api/prompts/{name}")
def update_prompt(name: str, prompt: PromptUpdate):
    """Commit a new version of an existing prompt."""
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    if not prompt.notes.strip():
        raise HTTPException(400, "Commit notes are required.")
    versions = db["prompts"][name]
    last = versions[-1]
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
    db["prompts"][name].append(entry)
    save_db(db)
    return {"name": name, "version": new_version, "hash": entry["hash"]}


@app.get("/api/prompts/{name}")
def get_prompt(name: str, version: Optional[int] = Query(None)):
    """Get a specific prompt (optionally pinned to a version)."""
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
    """Get full version history of a prompt."""
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    return {"name": name, "versions": db["prompts"][name]}


@app.get("/api/prompts/{name}/diff")
def diff_versions(name: str, v1: int = Query(...), v2: int = Query(...)):
    """Get a unified diff between two versions."""
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    versions = db["prompts"][name]
    max_v = len(versions)
    if not (1 <= v1 <= max_v and 1 <= v2 <= max_v):
        raise HTTPException(400, f"Versions must be between 1 and {max_v}.")
    a = versions[v1 - 1]["content"].splitlines(keepends=True)
    b = versions[v2 - 1]["content"].splitlines(keepends=True)
    diff = list(difflib.unified_diff(a, b, fromfile=f"v{v1}", tofile=f"v{v2}"))
    return {"name": name, "v1": v1, "v2": v2, "diff": "".join(diff)}


@app.delete("/api/prompts/{name}")
def delete_prompt(name: str):
    """Delete a prompt and all its versions."""
    db = load_db()
    if name not in db["prompts"]:
        raise HTTPException(404, f"Prompt '{name}' not found.")
    del db["prompts"][name]
    save_db(db)
    return {"deleted": name}


@app.get("/api/tags")
def list_tags():
    """Return all unique tags across all prompts."""
    db = load_db()
    tags = set()
    for versions in db["prompts"].values():
        for v in versions:
            tags.update(v.get("tags", []))
    return sorted(tags)


# ── Seed data for demo ────────────────────────────────────────────────────────
@app.post("/api/seed")
def seed_demo():
    """Seed the vault with demo prompts for testing."""
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
            continue
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