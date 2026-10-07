# DEVRELAY.md — How to initialise and use DevRelay (with Claude Code)

DevRelay (https://devrelay.com, **beta**, v0.1.18 when this was written) is an **MCP server + skill pack** that connects your coding agent (Claude Code, Cursor, Codex, etc.) to **DEV** and **MLH**. For this project it lets you:
- check the challenge's current dates/rules from inside the session,
- search DEV posts for fixes to problems you hit,
- check/claim sponsor credits (only at MLH events you've joined),
- **save the agent session** and embed it in your post (the challenge says this "helps the judges understand your process"),
- draft your DEV post from the repo, and enter challenges.

It asks you before it registers, claims, or publishes anything.

---

## 1. One-time setup

### 1.1 Install
**macOS / Linux**
```bash
curl -fsSL https://devrelay.com/install.sh | sh
```
**Windows:** open https://devrelay.com, click the **Windows** tab under "Install", and use the command shown there (I could not copy it from the page text, so don't guess).

What the installer does (per the site): installs the gateway + skills, registers DevRelay with every supported agent it finds, and checks for updates daily.

> Tip: read the script first if you like: `curl -fsSL https://devrelay.com/install.sh | less`.

### 1.2 Restart your agent
Fully quit and reopen Claude Code (new terminal session) so it loads the new MCP server.

### 1.3 Sign in with MLH
The first time your agent uses DevRelay, your browser opens to sign in with **MLH**.
To publish on DEV, **link your DEV account in your MLH profile** (otherwise drafts/publishing won't work).

### 1.4 Verify it's connected
In a terminal:
```bash
claude mcp list
```
You should see `devrelay-gateway` listed. Inside Claude Code you can also type `/mcp` to see MCP servers and their status.

Then ask Claude Code:
```
Using DevRelay, what DEV challenges are open right now? List the Touch Grass one with its deadline and submission requirements.
```
If it returns challenge info, you're set.

### 1.5 Manual config (only if the installer didn't register it)
Add this to your MCP client config (the installer normally writes it for you), using the **full path** to the binary:
```json
{
  "mcpServers": {
    "devrelay-gateway": {
      "command": "~/.devrelay/bin/dev_mlh_mcp_server",
      "args": ["--stdio"]
    }
  }
}
```
For Claude Code you can also register by CLI. Check `claude mcp add --help` for the current syntax, e.g. (verify flags on your version):
```bash
claude mcp add devrelay-gateway -- ~/.devrelay/bin/dev_mlh_mcp_server --stdio
```

---

## 2. What DevRelay can do (tools seen on the site)
`get_challenges`, `get_events`, `get_mlh_event`, `list_event_offers`, `search_dev_to_semantic`, `create_article` (drafts), `submit_project_to_event`, `enter_challenge`, plus a "share the session" capability. You normally don't call tools by name. Just ask in plain language and approve when it asks.

Important about **sponsor credits**: offers are tied to **MLH events you've joined**. Ask whether the Touch Grass challenge has any; if not, claim nothing and check each partner's own free tier/credits page (Render, ElevenLabs, MongoDB Atlas, Sentry, Tinker).

---

## 3. How to use it in this project

### Day 0 (right after install)
```
Using DevRelay: (1) give me the exact deadline and submission requirements for the DEV Touch Grass challenge, including required tags/template and which partner prize categories exist; (2) tell me if any sponsor offers are available to me for Render, ElevenLabs, MongoDB Atlas, Sentry or Tinker; do NOT claim anything yet; (3) tell me if one project can be entered in multiple partner categories.
```
Record answers in `docs/DECISIONS.md`.

### While building (stuck on something)
```
Search DEV via DevRelay for posts about "<specific problem>" (e.g., llama.cpp server on a CPU-only container, MongoDB Atlas vector search $in filter, MediaPipe Gemma-3n web). Summarize what worked, cite the posts, and apply only what fits our MASTERSPEC.
```

### End of every work session
```
Summarize today's decisions and open questions into docs/DECISIONS.md. Then save this agent session using DevRelay and give me the link/embed. Don't publish anything.
```

### Draft the post (Day 7)
```
Using DevRelay, create a DEV *draft* (published: false) for the Touch Grass challenge from this repo. Follow the outline in PROJECTPLAN.md §8, use only claims backed by evals/ and the claims ledger, include the architecture diagram as an image placeholder, and embed my saved agent session(s). Mark it AI-assisted. Show me the draft before anything is published.
```
Then **rewrite it in your own voice** (writing quality is the top criterion).

### Enter the challenge / submit
Only after you've reviewed the post:
```
Using DevRelay, enter this post in the Touch Grass challenge and the partner categories I actually used: <list>. Show me exactly what will be submitted and wait for my explicit "yes".
```

---

## 4. Saving and embedding the agent session
- Ask Claude Code (with DevRelay) to **save the session transcript to DEV** and give you the embed link, or link to it from the post.
- Save **multiple focused sessions** (e.g., "Render deploy", "Tinker eval", "Gemma verifier") rather than one giant one. Each should end with the DECISIONS summary.
- In the post, add 1–2 sentences per session on what judges will see (a key prompt, a bug found via Sentry, a design decision).

### Before you save or publish a session, check for secrets
- [ ] No API keys, tokens, connection strings (Atlas URI, ElevenLabs, Sentry DSN, HF token, Tinker key) appear in the transcript.
- [ ] No personal location data (home address, precise coordinates) or phone numbers.
- [ ] No friends' names or photos without permission.
- If a secret slipped in: **rotate it now**, then redact/delete the saved session if possible.

Prevention: keep secrets in `.env`/Render env only; tell Claude to refer to env var *names*; don't `cat .env` in the session.

---

## 5. Troubleshooting
| Symptom | Fix |
|---|---|
| `claude mcp list` doesn't show DevRelay | Re-run installer; restart terminal and Claude Code; add manual config (1.5) |
| Browser sign-in loops | Sign in at MLH first, then retry; check you're using the same browser profile |
| "DEV account not linked" / can't create drafts | Link DEV in your MLH profile, then retry |
| Offers say "ineligible" | Offers are for MLH events you've joined, new accounts only for some; don't claim anything unclear |
| Tool not found / outdated | The installer auto-updates daily; re-run the installer to force an update |
| Binary not executable | Check `~/.devrelay/bin/dev_mlh_mcp_server` exists and has execute permission (`chmod +x`) |

## 6. Rules of the road
- DevRelay is **beta**: verify anything it tells you about deadlines/rules against the official challenge page.
- Never let any agent publish, register, or claim without you reading what it will send.
- The post must be yours: use the draft as scaffolding, not as the final text.
