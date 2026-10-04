from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
generated = root / "build" / "desktop"
datas = [
    (str(root / "dist"), "dist"),
    (str(generated / "release-channel.json"), "."),
    (str(generated / "THIRD_PARTY_NOTICES.txt"), "."),
    (str(root / "package.json"), "."),
    (str(root / "desktop" / "install-update.ps1"), "desktop"),
    (str(root / ".agents" / "skills"), ".agents/skills"),
    (str(root / ".claude" / "skills"), ".claude/skills"),
    (str(root / "docs"), "docs"),
    (str(root / "README.md"), "."),
    (str(root / "AGENTS.md"), "."),
    (str(root / "CLAUDE.md"), "."),
]
datas += copy_metadata("mcp")
gui = Analysis([str(root / "desktop" / "main.py")], pathex=[str(root)],
               datas=datas)
mcp = Analysis([str(root / "desktop" / "mcp_entry.py")], pathex=[str(root)])
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True,
              name="Agentboard", console=False, upx=False,
              version=str(generated / "version-info.txt"))
mcp_exe = EXE(PYZ(mcp.pure), mcp.scripts, [], exclude_binaries=True,
              name="AgentboardMCP", console=True, upx=False,
              version=str(generated / "version-info.txt"))
COLLECT(gui_exe, mcp_exe, gui.binaries, gui.datas, mcp.binaries, mcp.datas,
        name="Agentboard", upx=False)
