"""MCP tools for the shared Agentboard HTTP API; never opens the database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ROOT = Path(__file__).resolve().parents[1]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Key = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Description = Annotated[str, StringConstraints(max_length=50000)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200000)]
Version = Annotated[int, Field(ge=1)]
Limit = Annotated[int, Field(ge=1, le=100)]
Status = Literal["backlog", "in_progress", "review", "done", "blocked"]
Priority = Literal["urgent", "high", "medium", "low"]
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

INSTRUCTIONS = (
    "Use this shared board to track work. Read list_projects/get_board/get_task before editing. "
    "Create tasks with rationale and acceptance criteria, then claim before work. "
    "After each significant code edit call log_change; record checks as evidence notes. "
    "Use review before done. Every write needs a concise reason and a unique idempotency_key. "
    "Retry the same payload with the SAME key after network errors. On HTTP409 read fresh version; "
    "do not overwrite stale work. Actor comes from credentials. Never put secrets or hidden reasoning in notes. "
    "Renew your lease with claim_task and fresh version. Reads and note-write replies return bounded previews; "
    "task summaries preview dependency IDs (get_task keeps them all), history snapshots/notes preview long text and files. "
    "dashboard export retains full history. last_seen means last API request, not a running agent session."
)


class TaskChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    description: Description | None = None
    rationale: Reason | None = None
    acceptance_criteria: Description | None = None
    status: Status | None = None
    priority: Priority | None = None
    assignee_id: Identifier | None = None
    section_id: Identifier | None = None
    depends_on: list[Identifier] | None = Field(default=None, max_length=128)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Credentials must never follow an HTTP redirect to another origin.
        return None


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Agentboard URL must be a loopback HTTP origin, e.g. http://127.0.0.1:4242")
    parsed.port  # Validate a malformed port before any network request.
    return url.rstrip("/")


def default_data_dir() -> Path:
    """Installed clients keep personal state outside the application bundle."""
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Agentboard"
    return ROOT / "data"


def connection_options(credentials: Path | None = None, data_dir: Path | None = None,
                       url: str | None = None) -> tuple[Path, str]:
    if data_dir is None and getattr(sys, "frozen", False):
        data_dir = default_data_dir()
    if data_dir is not None:
        data_dir = data_dir.resolve()
        if url is None:
            runtime = json.loads((data_dir / "runtime.json").read_text(encoding="utf-8-sig"))
            if not isinstance(runtime, dict) or not isinstance(runtime.get("base_url"), str):
                raise ValueError("Invalid Agentboard runtime.json; start the desktop application")
            url = runtime["base_url"]
    credentials = (credentials or (data_dir or default_data_dir()) / "connector-secrets.json").resolve()
    return credentials, validate_url(url or "http://127.0.0.1:4242")


def load_token(agent: str, credentials: Path, token_file: Path | None = None) -> tuple[str, str]:
    if token_file:
        content = token_file.read_text(encoding="utf-8-sig").strip()
        if content.startswith("{"):
            issued = json.loads(content)
            token = issued.get("token")
            actor_id = issued.get("agent", {}).get("id", agent)
        else:
            token, actor_id = content, agent
    elif os.environ.get("AGENTBOARD_TOKEN"):
        token, actor_id = os.environ["AGENTBOARD_TOKEN"].strip(), agent
    else:
        content = json.loads(credentials.read_text(encoding="utf-8-sig"))
        if content.get("schema_version") != 1:
            raise ValueError("Unsupported Agentboard credentials schema")
        entry = content.get("agents", {}).get(agent)
        if not isinstance(entry, dict):
            raise ValueError(f"No credentials for {agent}; start Agentboard or use --token-file")
        token, actor_id = entry.get("token"), entry.get("id", agent)
    if not isinstance(token, str) or not token or len(token) > 4096 or "\r" in token or "\n" in token:
        raise ValueError("Agentboard token is missing or invalid")
    return token, actor_id


def clipped(value: Any, maximum: int = 4000) -> Any:
    """Bound text while keeping IDs and JSON shape; full data stays on the API."""
    if isinstance(value, str):
        return value if len(value) <= maximum else value[:maximum] + "\n… [truncated; full data in dashboard export]"
    if isinstance(value, list):
        return [clipped(item, maximum) for item in value]
    if isinstance(value, dict):
        return {key: clipped(item, maximum) for key, item in value.items()}
    return value


def task_summary(task: dict) -> dict:
    fields = (
        "id", "short_id", "project_id", "section_id", "title", "status", "priority", "version",
        "assignee_id", "depends_on", "claim_owner_id", "claim_expires_at", "updated_at",
    )
    result = {field: task.get(field) for field in fields}
    dependencies = task.get("depends_on", [])
    result.update(depends_on=dependencies[:10], depends_on_count=len(dependencies),
                  depends_on_truncated=len(dependencies) > 10)
    return result


def note_summary(note: dict) -> dict:
    result = {field: note.get(field) for field in ("id", "task_id", "kind", "body", "actor_id", "created_at")}
    result["body"] = clipped(result["body"], 500)
    metadata = note.get("metadata") or {}
    files = metadata.get("files", [])
    result["metadata"] = {"files": clipped(files[:5], 160), "files_total": len(files),
                          "files_truncated": len(files) > 5,
                          **{field: clipped(metadata.get(field), 500) for field in ("diff", "commit", "verification")}}
    result["summary_only"] = True
    return result


def event_summary(event: dict) -> dict:
    result = {field: value for field, value in event.items() if field not in {"before", "after"}}
    before, after = event.get("before") or {}, event.get("after") or {}
    result["changed_fields"] = sorted(field for field in set(before) | set(after) if before.get(field) != after.get(field))
    for field in ("before", "after"):
        snapshot = event.get(field)
        result[field] = None if snapshot is None else (
            note_summary(snapshot) if event.get("entity_type") == "note" else
            task_summary(snapshot) if event.get("entity_type") == "task" else clipped(snapshot, 500)
        )
    result["snapshots_are_summaries"] = True
    return clipped(result, 500)


def build_server(base_url: str, token: str, actor_id: str, session_id: str) -> FastMCP:
    base_url = validate_url(base_url)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    server = FastMCP("agentboard", instructions=INSTRUCTIONS)

    def api(method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(base_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {token}", "X-Session-ID": session_id,
            "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with opener.open(request, timeout=15) as response:
                result = json.load(response)
                if not isinstance(result, dict):
                    raise ToolError("INVALID_API_RESPONSE: expected a JSON object")
                return result
        except HTTPError as error:
            raw = error.read(8192).decode("utf-8", errors="replace")
            try:
                message = json.loads(raw).get("detail", raw)
            except (ValueError, AttributeError):
                message = raw or error.reason
            message = str(message).replace(token, "[redacted]")[:2000]
            hint = " Read the latest task/version before retrying." if error.code == 409 else ""
            raise ToolError(f"HTTP_{error.code}: {message}.{hint}") from None
        except (URLError, TimeoutError, OSError) as error:
            detail = str(error).replace(token, "[redacted]")[:300]
            raise ToolError(
                f"API_UNREACHABLE: start Agentboard at {base_url}. {detail}. "
                "If a write may have reached the server, retry its identical payload and idempotency_key."
            ) from None
        except (ValueError, UnicodeError):
            raise ToolError("INVALID_API_RESPONSE: server did not return valid JSON") from None

    def entity_path(kind: str, entity_id: str) -> str:
        return f"/api/{kind}/{quote(entity_id, safe='')}"

    @server.tool(annotations=READ)
    def list_projects(limit: Limit = 50, offset: Annotated[int, Field(ge=0)] = 0,
                      query: str = "", agent_limit: Limit = 20,
                      agent_offset: Annotated[int, Field(ge=0)] = 0) -> dict[str, Any]:
        """Find projects and agent identities. Page projects with offset and identities with agent_offset."""
        data = api("GET", "/api/bootstrap")
        projects = [project for project in data["projects"] if not query or query.casefold() in project["name"].casefold()]
        end = offset + limit
        agent_end = agent_offset + agent_limit
        return clipped({"projects": projects[offset:end], "total": len(projects),
                        "next_offset": end if end < len(projects) else None,
                        "agents": [{field: agent.get(field) for field in ("id", "name", "kind", "last_seen")}
                                   for agent in data["agents"][agent_offset:agent_end]],
                        "total_agents": len(data["agents"]),
                        "next_agent_offset": agent_end if agent_end < len(data["agents"]) else None})

    @server.tool(annotations=WRITE)
    def create_project(name: Title, reason: Reason, idempotency_key: Key,
                       description: Description = "",
                       repository: Annotated[str, Field(max_length=2048)] = "",
                       color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#7c8aff") -> dict[str, Any]:
        """Create a persistent project board. Supply the same key AND payload when retrying."""
        return clipped(api("POST", "/api/projects", {
            "name": name, "description": description, "repository": repository, "color": color,
            "reason": reason, "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=READ)
    def get_board(project_id: Identifier, limit: Limit = 50,
                  status: Status | None = None, section_id: Identifier | None = None,
                  assignee_id: Identifier | None = None, query: str = "", offset: Annotated[int, Field(ge=0)] = 0,
                  section_limit: Limit = 20, section_offset: Annotated[int, Field(ge=0)] = 0) -> dict[str, Any]:
        """Read bounded section/task summaries. section_id includes that section's description. offset and section_offset page lists."""
        data = api("GET", entity_path("projects", project_id))
        tasks = [task for task in data["tasks"] if
                 (status is None or task["status"] == status)
                 and (section_id is None or task["section_id"] == section_id)
                 and (assignee_id is None or task["assignee_id"] == assignee_id)
                 and (not query or query.casefold() in (task["title"] + " " + task["short_id"]).casefold())]
        end = offset + limit
        section_end = section_offset + section_limit
        return clipped({
            "project": data["project"],
            "sections": [{field: section.get(field) for field in ("id", "project_id", "title", "version", "updated_at")}
                         for section in data["sections"][section_offset:section_end]],
            "total_sections": len(data["sections"]),
            "next_section_offset": section_end if section_end < len(data["sections"]) else None,
            "section_context": next((section for section in data["sections"] if section["id"] == section_id), None),
            "tasks": [task_summary(task) for task in tasks[offset:end]], "total": len(tasks),
            "next_offset": end if end < len(tasks) else None,
            "activity": [event_summary(event) for event in data["activity"][:10]],
        }, 2000)

    @server.tool(annotations=READ)
    def ready_tasks(project_id: Identifier, limit: Limit = 20,
                    section_id: Identifier | None = None) -> dict[str, Any]:
        """Find unblocked backlog/in-progress tasks with no live lease. Claim atomically before working."""
        data = api("GET", entity_path("projects", project_id))
        by_id = {task["id"]: task for task in data["tasks"]}
        ready = []
        instant = datetime.now(timezone.utc)
        for task in data["tasks"]:
            if task["status"] not in {"backlog", "in_progress"} or (section_id and task["section_id"] != section_id):
                continue
            if any(by_id.get(dependency, {}).get("status") != "done" for dependency in task["depends_on"]):
                continue
            expires = task.get("claim_expires_at")
            if task.get("claim_owner_id") and expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) > instant:
                continue
            ready.append(task)
        priority = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        ready.sort(key=lambda task: (priority[task["priority"]], task["created_at"], task["id"]))
        return {"tasks": [task_summary(task) for task in ready[:limit]], "total": len(ready)}

    @server.tool(annotations=WRITE)
    def create_section(project_id: Identifier, title: Title, reason: Reason, idempotency_key: Key,
                       description: Description = "") -> dict[str, Any]:
        """Create a project section for one major task/workstream. Individual tasks belong to this section."""
        return clipped(api("POST", entity_path("projects", project_id) + "/sections", {
            "title": title, "description": description, "reason": reason, "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=WRITE)
    def create_task(project_id: Identifier, section_id: Identifier, title: Title, rationale: Reason,
                    reason: Reason, idempotency_key: Key, description: Description = "",
                    acceptance_criteria: Description = "", priority: Priority = "medium",
                    assignee_id: Identifier | None = None,
                    depends_on: Annotated[list[Identifier], Field(max_length=128)] | None = None) -> dict[str, Any]:
        """Create a task with purpose and acceptance criteria. Dependencies must belong to this project."""
        return clipped(api("POST", "/api/tasks", {
            "project_id": project_id, "section_id": section_id, "title": title, "rationale": rationale,
            "description": description, "acceptance_criteria": acceptance_criteria, "priority": priority,
            "assignee_id": assignee_id, "depends_on": depends_on or [],
            "reason": reason, "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=READ)
    def get_task(task_id: Identifier, note_limit: Limit = 10, event_limit: Limit = 10) -> dict[str, Any]:
        """Read current version, rationale, criteria and all dependency IDs with recent note/event summaries. Long text is clipped."""
        data = api("GET", entity_path("tasks", task_id))
        return clipped({"task": data["task"], "notes": [note_summary(note) for note in data["notes"][-note_limit:]],
                        "events": [event_summary(event) for event in data["events"][:event_limit]],
                        "note_total": len(data["notes"]), "event_total": len(data["events"])})

    @server.tool(annotations=WRITE)
    def update_task(task_id: Identifier, expected_version: Version, changes: TaskChanges,
                    reason: Reason, idempotency_key: Key) -> dict[str, Any]:
        """Update a freshly read task. Review before done; done requires criteria and an evidence note. 409 never overwrites."""
        payload = changes.model_dump(exclude_unset=True)
        if not payload:
            raise ToolError("VALIDATION_ERROR: changes must contain at least one field")
        return clipped(api("PATCH", entity_path("tasks", task_id), {
            "expected_version": expected_version, "changes": payload, "reason": reason,
            "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=WRITE)
    def claim_task(task_id: Identifier, expected_version: Version, reason: Reason, idempotency_key: Key,
                   lease_seconds: Annotated[int, Field(ge=30, le=86400)] = 3600) -> dict[str, Any]:
        """Atomically claim unblocked work as the authenticated agent, or renew your own lease with a fresh version."""
        return clipped(api("POST", entity_path("tasks", task_id) + "/claim", {
            "expected_version": expected_version, "lease_seconds": lease_seconds,
            "reason": reason, "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=WRITE)
    def add_note(task_id: Identifier, kind: Literal["progress", "decision", "evidence", "comment"],
                 body: Body, reason: Reason, idempotency_key: Key) -> dict[str, Any]:
        """Append progress, a decision, check evidence or a comment. Explain this event's reason separately from task rationale."""
        return note_summary(api("POST", entity_path("tasks", task_id) + "/notes", {
            "kind": kind, "body": body, "reason": reason, "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=WRITE)
    def log_change(task_id: Identifier, summary: Body,
                   files: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=2048)]], Field(min_length=1, max_length=200)],
                   reason: Reason, idempotency_key: Key,
                   diff: Annotated[str, Field(max_length=200000)] | None = None,
                   commit: Annotated[str, Field(max_length=2048)] | None = None,
                   verification: Description | None = None) -> dict[str, Any]:
        """Log a significant code edit: what files changed, why, optional diff/commit and verification. This tool does not edit or inspect files."""
        return note_summary(api("POST", entity_path("tasks", task_id) + "/changes", {
            "summary": summary, "files": files, "diff": diff, "commit": commit,
            "verification": verification, "reason": reason, "idempotency_key": idempotency_key,
        }))

    @server.tool(annotations=READ)
    def get_history(project_id: Identifier | None = None, task_id: Identifier | None = None,
                    after: Annotated[int, Field(ge=0)] = 0, limit: Limit = 50) -> dict[str, Any]:
        """Read history summaries in ascending event ID order. Continue with next_cursor as after; snapshots preview changed fields and files."""
        params = {"after": after, "limit": limit}
        if project_id:
            params["project_id"] = project_id
        if task_id:
            params["task_id"] = task_id
        data = api("GET", "/api/history?" + urlencode(params))
        return {"events": [event_summary(event) for event in data["events"]], "next_cursor": data["next_cursor"]}

    @server.tool(annotations=READ)
    def connector_status() -> dict[str, Any]:
        """Check this connector's API reachability. Returns no credentials; configured actor label is not a verified live session."""
        return {"api": api("GET", "/api/health"), "base_url": base_url,
                "configured_identity": actor_id, "session_id": session_id, "transport": "stdio"}

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=["codex", "claude"], required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--data-dir", type=Path, help="Read current loopback URL from this desktop data directory")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--url", help="Explicit loopback URL; overrides desktop runtime discovery")
    parser.add_argument("--session-id", default=os.environ.get("AGENTBOARD_SESSION_ID") or f"mcp-{uuid4()}")
    args = parser.parse_args(argv)
    try:
        credentials, base_url = connection_options(args.credentials, args.data_dir, args.url)
        token, actor_id = load_token(args.agent, credentials, args.token_file)
        if not args.session_id or len(args.session_id) > 200 or "\n" in args.session_id or "\r" in args.session_id:
            raise ValueError("Invalid session ID: use 1–200 characters without line breaks")
        build_server(base_url, token, actor_id, args.session_id).run(transport="stdio")
    except (OSError, ValueError, KeyError) as error:
        print(f"Agentboard connector: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
