# Third-party notices

Aktapokus AI Studio itself is MIT licensed (see `LICENSE`). It bundles the following third-party files under
`aktapokus_ai_studio/web/vendor/` (full license texts are in the same folder):

| Component | Version | License | Source |
| --- | --- | --- | --- |
| xterm.js (`xterm.js`, `xterm.css`) | 6.0.0 | MIT | https://github.com/xtermjs/xterm.js |
| xterm-addon-fit (`addon-fit.js`) | 0.11.0 | MIT | https://github.com/xtermjs/xterm.js |
| Inter variable font (`inter-*.woff2`) | 5.3.0 (@fontsource-variable/inter) | SIL Open Font License 1.1 | https://github.com/rsms/inter |
| Lora font (`Lora/*.ttf`) | Google Fonts release | SIL Open Font License 1.1 (Reserved Font Name "Lora"; text in `Lora/OFL.txt`) | https://github.com/cyrealtype/Lora-Cyrillic |

The fonts are distributed unmodified. Under the OFL they may be bundled with this software but not sold on their own.

Integrity hashes and download details: `aktapokus_ai_studio/web/vendor/SURUMLER.txt`.

## Optional Python packages (not bundled)

Installed only if you ask for them (`pip install -e ".[qr]"` / `".[opcua]"`); each keeps its own license:

| Package | Used for | License |
| --- | --- | --- |
| segno | Telegram pairing QR code | BSD-3-Clause |
| asyncua | OPC UA client / test server | LGPL-3.0 (used as an unmodified, separately installed library) |
| pytest, pytest-timeout | Development tests only | MIT |

## Tools this project drives but does NOT include

Aktapokus AI Studio orchestrates programs that you install yourself, each under its own license and terms of service:
OpenCode, Claude Code, OpenAI Codex CLI, Gemini CLI, Google Antigravity CLI, Mistral Vibe, DeepSeek Harness, GitHub CLI
(`gh`), `git`, Tailscale, and any MCP servers or custom CLIs you add. Node-RED (Apache-2.0) is downloaded from npm only
when you enable it. Telegram and Google (Gmail, Drive, Calendar) are reached through their public APIs with your own
bot token / OAuth client.

## Trademarks

All product names, service names and logos shown in the user interface (for example Google, Gmail, Google Drive,
Google Calendar, GitHub, Telegram, Claude, Gemini, Mistral, DeepSeek, OpenAI) are trademarks of their respective
owners. They are used only to identify the service a button or setting connects to. They are **not** covered by this
project's MIT license, and this project is not affiliated with, endorsed by, or sponsored by any of those owners.
