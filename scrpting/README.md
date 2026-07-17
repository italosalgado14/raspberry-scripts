# tmux on the Raspberry Pi

A short guide for using **tmux** to keep tasks running on the Pi after you
disconnect. You SSH in, start something inside a tmux session (docker, Claude
Code, a long script), detach, and close your laptop — the task keeps running.
Next time you SSH in, you re-attach and find it exactly where you left it.

```
sudo apt install tmux
```

> To *start* tasks automatically at a certain hour (cron), see
> [SCHEDULING.md](SCHEDULING.md).

## The one idea that matters

A tmux **session** is a terminal that lives on the Pi, not in your SSH
connection. Give each task its own named session:

```
tmux new -s claude       # create a session called "claude" and enter it
# ... run whatever you want inside ...
# detach: press  Ctrl-b  then  d      (session keeps running)

tmux ls                  # list sessions
tmux attach -t claude    # come back to it
tmux kill-session -t claude   # stop it for good
```

That's 90% of daily use.

## Recipes

**Start docker and forget about it** (starts detached, you never even enter):

```
tmux new -d -s docker 'cd ~/myapp && docker compose up'
tmux attach -t docker        # only if you want to watch the logs
```

**A console dedicated to Claude Code:**

```
tmux new -s claude
claude                       # work with it, then Ctrl-b d to detach
```

Claude keeps working on its task while you're disconnected; re-attach later to
see the result.

**Watch a log on the side:**

```
tmux new -d -s logs 'journalctl -f'
```

Or use the `t` helper script in this folder, which wraps the
create-or-attach dance:

```
./t claude                          # attach if it exists, create if not
./t docker 'cd ~/myapp && docker compose up'   # create detached with a command
./t                                 # list sessions
```

## Keys cheatsheet (all start with `Ctrl-b`)

| Keys | Action |
|------|--------|
| `Ctrl-b d` | Detach (leave session running) |
| `Ctrl-b c` | New window (tab) inside the session |
| `Ctrl-b n` / `p` | Next / previous window |
| `Ctrl-b %` | Split pane vertically |
| `Ctrl-b "` | Split pane horizontally |
| `Ctrl-b` + arrows | Move between panes |
| `Ctrl-b [` | Scroll mode (`q` to exit) |
| `Ctrl-b x` | Kill current pane |

## Good habits

- **One session per task**, named after the task (`docker`, `claude`, `logs`).
  `tmux ls` then reads like a status board of what the Pi is doing.
- If a session ends the moment you create it, the command inside crashed — run
  the command manually first to check it works.
- tmux survives SSH drops, **not reboots**. For things that must come back
  after a power cut, use a systemd service or a `@reboot` cron line, e.g.:

  ```
  @reboot tmux new -d -s docker 'cd ~/myapp && docker compose up'
  ```
