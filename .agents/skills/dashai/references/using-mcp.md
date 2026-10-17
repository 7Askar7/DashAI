# Working through MCP

Use the DashAI tools exposed by the user's client (commonly under `agentboard`). Do not discover or read local token files to work around an authorization error. If the connector is absent or returns 401, report that limitation and continue independent repository work when useful.

For project work, use `list_projects`, then `get_board` and the relevant `get_task`. Create a task with its real `project_id`, rationale, acceptance criteria and `task_type`; choose an existing `subproject_id` for a workstream, or create one within that project if the task needs it. Claim with the current version before execution.

After a meaningful change, `log_change` records files, a concise reason and available diff/commit/verification. It does not inspect Git or run commands. Save observed results with `add_note(kind="evidence")`; separate a decision from a check. Move through `review` before `done` after the work and its checks pass.

Each write has a new `idempotency_key`; retry the identical payload with the same key after a transport error. After 409 read the current state and reconcile before issuing a new intent. `claim_task` also renews an owned lease with a fresh version. The server derives the author from the credential; `session_id` only groups a process/chat's events.

For architecture documentation, read `get_project_map` and the actual source in the authorized workspace. Publish a complete safe file manifest with source hashes and structured descriptions through `publish_project_map`, preserving descriptions/diagrams according to the tool schema. Exclude secrets, dependency directories, build outputs and private data. Explain the purpose, behavior and dependencies of a file; do not present a guess as verified source behavior. Use supported diagram notation and explicit `source_revision`; the board does not monitor the filesystem or generate model output by itself.

`list_modules` and `get_project_modules` expose reusable Markdown templates and project settings. `configure_project_module` uses the current version; omitting content preserves it, an empty string clears it. Disabling a module keeps its content. Use `create_module_template` for a user-requested reusable document, not an executable plugin. External publication requires the user's configured destination and allowed scope; never infer a broader destination from a URL or a model's suggestion.

For the optional `releases` module, use `list_project_releases`, `get_project_release`, `create_project_release` and `update_project_release`. Read the full record and current version before editing. A release records the user's or agent's stated version, environment, date and changes; it is not proof that deployment ran or production is healthy. Disabling the module preserves history and exports. See `docs/project-releases.md` for field limits and date rules.

For large results, follow `next_offset` / `next_cursor`. Responses contain bounded previews; use detail tools and the dashboard export when full text is required. `connector_status` verifies API reachability from this MCP process. `last_seen` indicates a request, not a currently running model or a verified vendor.
