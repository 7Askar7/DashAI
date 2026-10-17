# DashAI

![DashAI cover](https://raw.githubusercontent.com/7Askar7/DashAI/main/public/brand/dashai-cover.png)

A local project workspace for people and coding agents with stdio MCP support. Organize projects, subprojects, and tasks, explain your repository, document architecture, and track changes and decisions directly in VS Code. Give each agent a name that makes sense for your team; client configuration is independent from the model's name.

**Windows 10/11 x64 or macOS Apple Silicon / Intel · VS Code 1.95+ · Russian interface.** Each platform has its own native package. Python, Node.js, and a separate desktop installation are not required. Your project database and history stay on your computer; optional integrations send only the documentation you enable to your chosen destination.

## Open your board

After installing, select **DashAI** in the Activity Bar → **Открыть доску**, or use the Command Palette → **DashAI: Открыть доску**.

Create a project and optional nested subprojects, such as Website → Payments → Testing. Every task stays on one shared project board, grouped by status. Select the subproject and work type separately when creating or editing a task. Filters include the selected subproject's descendants.

## Connect your coding agents

Open **Коннекторы** to create a separately named identity and choose a ready configuration for Codex, Claude Code, Cursor, VS Code/Copilot, Cline, or another stdio MCP client. Keep the issued token file outside Git; configuration references its path instead of embedding the token. Install your preferred client separately and start a new session after setup.

The existing **DashAI: Подключить Codex и Claude Code** command remains a shortcut for preparing those two project-scoped configurations in a trusted local folder. It preserves your other settings. Approve the project MCP connection if your client asks. DashAI is an independent project and is not affiliated with the model or client providers.

Agents share the same local API and store as the dashboard. They can create and claim tasks, explain decisions, log file changes, and attach verification evidence. The history records the author, session, reason, and before/after values. A configuration file alone does not prove that an agent has connected.

## Project map and documentation

Open **Карта проекта** to browse a published file tree with explanations of what each file does, how it works, and why it exists. Large maps show a scrolling window of rows, with search across paths and explanations, folder counts, a reveal-selected action, and keyboard navigation. Search results include full paths so similarly named files are easy to distinguish.

**Архитектура** renders Mermaid diagrams: C4 context/containers/components, UML sequence/state, ERD, and flowcharts. **Документация** saves your selection of sections and diagrams, includes enabled document modules, and exports Markdown or a standalone HTML document through VS Code's save dialog.

**Задача на анализ** creates a documentation task for an external agent. The agent reads your allowed repository and publishes a versioned snapshot through MCP; DashAI does not start a model or watch source files automatically. Changed hashes mark affected explanations and diagrams for updating. Human review, revision history, and project export preserve the authorship and context of the documentation.

## Add only the modules your project needs

Open **Модули** inside a project to add or remove its features. Project map, architecture, and documentation are enabled initially; the board and history remain available. Removing a module hides its view while keeping its text and history.

Use the decision-record, risk, and runbook templates, or create a reusable Markdown module for your own process. Each project keeps its own content. These are documentation modules, not executable plugins or model runners.

## Optional personal Confluence and Jira connections

Enable **Confluence и Jira** only in the project that needs it. Paste a link to an existing Confluence root page or Jira project and provide your personal credentials. Both Atlassian Cloud and Data Center have concrete REST adapters. The root is checked through the service API before the connection is saved.

Enabled descriptions, diagrams, and document modules sync one way: Confluence pages are created only directly beneath the selected root, and Jira issues remain inside the selected project. DashAI does not create Atlassian spaces or projects. The UI shows queued work, failures, uncertain results, and conflicts; manual remote edits are protected. Mermaid is published as source text, not promised as a native Atlassian diagram.

Credentials remain in separate local files and are excluded from the database, history, and exports. Cloud API-token mode is an explicitly personal connection, not a public vendor OAuth implementation. See the [integration guide and limits](https://github.com/7Askar7/DashAI/blob/main/docs/integrations.md).

## Local data and updates

Personal data is stored separately from the extension: `%LOCALAPPDATA%\Agentboard` on Windows, or `~/Library/Application Support/Agentboard` on macOS. Updates and uninstalling the extension do not remove your project database. The optional Windows desktop app uses the same personal folder. DashAI does not run AI models or require their providers' API keys. Confluence/Jira credentials are needed only if you choose to connect those services.

After an update, VS Code may ask you to restart extensions. Existing agent sessions keep their version; new sessions use the updated companion without rewriting project configuration.

Local Windows and macOS folders are supported. Browser VS Code, virtual folders, and automatic agent setup inside SSH, WSL, or Dev Containers are not supported.

[Setup and connector guide](https://github.com/7Askar7/DashAI/blob/main/docs/vscode.md) · [Source code](https://github.com/7Askar7/DashAI) · [Support and issues](https://github.com/7Askar7/DashAI/issues)
