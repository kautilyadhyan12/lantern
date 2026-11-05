# 08 — Setup and First Steps

Pack 3.0 · written 2026-10-22 · read once at the start, then follow the backlog

You need **nothing installed on your laptop** except a web browser. Everything runs in a GitHub Codespace: a cloud computer with 8 GB of RAM that opens in your browser. The AI coding agent (Codex) works there.

## 1. What you need

| Thing | Cost | Notes |
|---|---|---|
| A GitHub account | free | github.com |
| A ChatGPT plan that includes Codex | Plus is the practical minimum | Free and Go plans allow only light Codex use; Plus has usage limits per 5 hours (`05` §11 says what to do when you hit them) |
| Codespaces hours | free up to 120 core-hours/month (about 60 hours on the 2-core machine) | with no payment method on file, usage simply stops at the limit, so there are no surprise bills |
| API keys for Lantern itself (from M1) | free tiers | Tavily (search), Groq, Cerebras, OpenRouter (models); later Copernicus, NASA FIRMS and others as packs need them |

## 2. Create the repository and open a codespace

1. On github.com: **New repository** → name `lantern` → **Public** → tick **Add a README file** → **Create repository**.
2. On the repository page: green **Code** button → **Codespaces** tab → **Create codespace on main**. Wait 1–2 minutes; an editor opens in your browser.
3. Drag `lantern-pack.zip` from your computer into the file list on the left of the editor.
4. Click into the terminal at the bottom and paste this line, then press Enter:

```
unzip -q lantern-pack.zip -d /tmp/pack && cp -r /tmp/pack/lantern/. . && rm lantern-pack.zip && git add -A && git commit -m "Add Lantern plan" && git push
```

5. Press **Ctrl+Shift+P**, type **Rebuild Container**, and choose **Codespaces: Rebuild Container**. This installs Python tools, Docker and Codex. It takes a few minutes, once.

The M0 setup correction pins the Microsoft image and installs Node, uv and
Codex through `.devcontainer/setup.sh`. It checks each official download's
checksum before unpacking any tool. This snapshot uses the existing tool
versions under the user-approved [ADR 0006](adr/ADR-0006-existing-workspace-tool-versions.md)
exception; the recorded tool warnings have not been declared fixed.
After creation, run `uv sync --frozen` in the repository to prepare its locked
Python 3.12 environment. Existing workspaces are not rebuilt automatically.

## 3. Sign in to Codex

In the terminal:

```
codex login --device-auth
```

Follow the link and enter the code with your ChatGPT account. If it says device login is not allowed, turn it on in ChatGPT's security settings, or run `codex` and choose **Sign in with ChatGPT**.

Then start Codex:

```
codex
```

When Codex asks whether to **trust this project**, say yes. Trusting it is what loads Lantern's settings and safety rules from `.codex/`.

## 4. The first prompt

Paste this into Codex:

```
Read AGENTS.md, then docs/00_START_HERE.md, docs/08_SETUP.md and the M0 section of
docs/06_ROADMAP_BACKLOG.md in full.
Tell me in plain English what Lantern is, what M0 will build, and what the first
story (S0.1) is. Do not start S0.1 yet. Wait for my yes.
```

After it explains, say **yes**. From then on the agent proposes each step and waits for your yes at every approval point.

## 5. The one-time M0 bootstrap (the agent follows this)

The proof tool (`make prove`) is built in S0.2, so S0.1 cannot be proved on its own. Instead:

1. Create the branch `story/M0-boot` from `main`.
2. **S0.1** on that branch: `$plan S0.1` → your yes → `$tests-first S0.1` → `$implement S0.1`. `$prove` does not exist yet, so `make check` is the check.
3. **S0.2** on the same branch: `$plan S0.2` → your yes → `$tests-first S0.2` → `$implement S0.2`.
4. Write `docs/plans/PLAN-M0.md` (goal: prove and review S0.1 and S0.2 together; ACs: both stories' ACs, verbatim), commit, and run `make prove STORY=M0 AC_STORIES="S0.1 S0.2"`.
5. **Review**: `$review M0`. The review tool arrives in S0.4, so the agent performs the steps of `05` §4.1–§4.2 by hand, with `{STORY}` = `M0`, `{STORY_SLUG}` = `m0`, `{ROUND}` = `1` (then `2`, `3` if more rounds are needed) and `{BASE}` = `main`, and shows you each command first. Fix, prove and review again until APPROVE (at most 3 rounds).
6. **Ship**: `$ship M0` opens a pull request from `story/M0-boot` titled `S0.1+S0.2: repository skeleton and proof kit`, and merges it after your yes. There is no CI yet; it arrives in S0.5.

This is the only exception to "one story per branch". From S0.3 on, every story follows the normal loop (`05` §1). S0.3 and S0.4 still use the by-hand review steps; S0.4 builds `make review`.

## 6. Every day after that

1. Open `github.com/<you>/lantern` → **Code** → **Codespaces** → click your codespace. It resumes where you left off.
2. In the terminal, run `codex`.
3. Tell it what you want, for example "Continue with the next step", or `$plan S1.3`.
4. When the agent says *"Everything is saved and pushed. You can close this tab."*, just close it.

GitHub stops the codespace after 30 minutes of inactivity and deletes codespaces left stopped for 30 days. Your work is always pushed to GitHub, so a deleted codespace loses nothing; you just create a new one the same way (steps 2 and 5 of §2).

## 7. API keys (when a story needs them, starting in M1)

The agent tells you which key a story needs and where to get it. To add one:

1. github.com → your profile picture → **Settings** → **Codespaces** → **Secrets** → **New secret**.
2. Name: exactly what the agent says (for example `LANTERN_GROQ_API_KEY`). Value: the key. Repository access: `lantern`.
3. Restart the codespace (Ctrl+Shift+P → **Codespaces: Stop Current Codespace**, then open it again) so the key appears.

Keys never go into files, and the agent never prints them.

## 8. Safety hooks (once, during S0.3)

When S0.3 adds Lantern's safety hooks, Codex asks you to trust them: type `/hooks` and approve them. Whenever a story must change Codex's own settings or CI files, the agent will ask you to restart Codex with:

```
LANTERN_ALLOW_HARNESS_EDITS=1 codex
```

for that one session.

## 9. If something goes wrong

- **"Usage limit reached" from Codex**: wait for the limit to reset (the message says when), or switch to a lighter model with `/model`.
- **The codespace will not start or feels stuck**: on the Codespaces page, choose **Stop**, then open it again. If it is broken, delete it and create a new one: all work is on GitHub.
- **You ran out of free Codespaces hours**: they reset monthly. You can see usage under GitHub → **Settings** → **Billing**.
