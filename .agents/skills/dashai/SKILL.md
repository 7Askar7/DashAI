---
name: dashai
description: Maintain the DashAI repository or use its MCP connector to track project work and publish architecture documentation. Use for DashAI tasks, project maps, documentation modules, and connector integration; it does not run or select AI models.
---

# DashAI

DashAI stores one shared project board and auditable documentation for humans and external coding agents. The MCP connector forwards to its local HTTP API; it never owns a separate project store. A client profile selects a configuration format. An identity names the credential's author; neither starts a model nor proves a connection.

- For changes to this repository, read [maintaining.md](references/maintaining.md), then follow the repository's `AGENTS.md` and the relevant implementation contract.
- For operating an existing board or publishing documentation through MCP, read [using-mcp.md](references/using-mcp.md). This works with any compatible stdio MCP client.

Keep source code, generated project descriptions, and observed verification distinct. A manifest's hash describes the analyzed snapshot; a saved configuration is not evidence that a client connected. Never copy credentials, private data, or raw secrets into project documentation or history.
