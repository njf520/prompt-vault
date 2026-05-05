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
from pydantic import BaseModel
from typing import Optional
import json
import os
import hashlib
from datetime import datetime, timezone
import difflib

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PromptVault",
    description="Version control for LLM prompts",
    version="1.0.0"
)

# ── Storage Setup ─────────────────────────────────────────────────────────────
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
class PromptCreate(BaseModel):
    """Shape of data required to create a new prompt (v1)."""
    name: str
    content: str
    tags: list[str] = []
    model_target: str = ""
    notes: str          # Required — commit message explaining why this prompt exists

class PromptUpdate(BaseModel):
    """Shape of data required to commit a new version of an existing prompt."""
    content: str
    tags: list[str] = []
    model_target: str = ""
    notes: str          # Required — must explain what changed and why


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the web UI."""
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
    """
    Create a new prompt at version 1.
    Returns a 400 error if a prompt with this name already exists.
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hash": make_id(prompt.content),
    }
    db["prompts"][prompt.name] = [entry]
    save_db(db)
    return {"name": prompt.name, "version": 1, "hash": entry["hash"]}


@app.put("/api/prompts/{name}")
def update_prompt(name: str, prompt: PromptUpdate):
    """
    Commit a new version of an existing prompt.
    Checks ALL fields for changes — not just content.
    Returns a 400 error if nothing actually changed.
    """
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
    """
    Get a prompt's content.
    Without ?version=N returns the latest. With ?version=2 returns that exact version.
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
    Same algorithm as Git. UI renders additions in green, deletions in red.
    """
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
    tags = set()
    for versions in db["prompts"].values():
        for v in versions:
            tags.update(v.get("tags", []))
    return sorted(tags)