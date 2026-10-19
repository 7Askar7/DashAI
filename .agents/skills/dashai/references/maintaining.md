# Maintaining the repository

Start with `AGENTS.md`, `docs/architecture.md`, the relevant `docs/research/` findings, and README commands. The repository instructions govern reviews and tracking; this skill provides the code map rather than a second policy.

| Area | Start here | Invariant |
| --- | --- | --- |
| HTTP and task domain | `server/app.py` | A mutation and its audit event commit together; stale versions fail rather than overwrite. |
| Project descriptions and diagrams | `server/project_map.py`, `src/ProjectMap.tsx`, `docs/project-map.md` | One manifest and immutable revisions; prose starts as a draft. |
| Optional project content | `server/modules.py` | Disabling a module preserves its content; user templates are Markdown, not executable plugins. |
| Release history | `server/releases.py`, `src/ProjectReleases.tsx`, `docs/project-releases.md` | A recorded release is user/agent input, not deployment evidence; preserve records when disabled and write audit atomically. |
| MCP tools and clients | `connectors/mcp_server.py`, `connectors/setup.py`, `connectors/presets.py`, `docs/connectors.md` | Use the common HTTP domain; keep client format independent from identity/model display name. |
| Desktop/runtime and releases | `desktop/runtime.py`, `desktop/mcp_entry.py`, `scripts/`, `docs/release.md`, `docs/vscode.md` | Personal data remains outside bundles; build and verify each native target. |
| UI and shared API types | `src/App.tsx`, `src/api.ts`, `src/styles.css` | Keep actual errors and unsaved edits visible; verify the user flow. |

Trace the affected UI → HTTP → domain → audit flow before editing. Reuse existing validation and stdlib facilities. Do not add a model runner, a second store, or speculative runtime dependencies. Agent identities can be assigned to tasks like the built-in identities, but only a human can issue credentials.

Keep shared navigation and form styles in `src/styles.css`. A lazily loaded feature stylesheet must not override the project shell after a user visits that feature.

Use the README's current commands. Focused checks include `python -m pytest tests/test_mcp.py -q` for the real stdio workflow and `npm run build` for production UI typing/build. A source test does not establish that a packaged native executable or an external service worked. Record the actual checks and material limitations. Only commit tracked source and deliberate documentation; exclude `data/`, local configs, tokens, and test profiles.
