# Scheduling tasks on the Raspberry Pi (cron)

Companion to [README.md](README.md): tmux keeps tasks running while you're
away; **cron** *starts* them for you at a given hour. Together they cover
"queue this to run at 22:00 and let me look at it tomorrow".

Cron is already installed on Raspberry Pi OS. Edit your schedule with:

```
crontab -e     # edit (first time it asks for an editor — pick nano)
crontab -l     # show what's scheduled
```

## The syntax

One line per task: five time fields, then the command.

```
┌───────── minute        (0-59)
│ ┌─────── hour          (0-23)
│ │ ┌───── day of month  (1-31)
│ │ │ ┌─── month         (1-12)
│ │ │ │ ┌─ day of week   (0-7, 0 and 7 = Sunday)
│ │ │ │ │
0 7 * * *  /home/pi/scripts/weather_notify.py
```

`*` means "every". Common patterns:

| Line starts with | Meaning |
|------------------|---------|
| `0 7 * * *` | every day at 07:00 |
| `30 22 * * *` | every day at 22:30 |
| `*/15 * * * *` | every 15 minutes |
| `0 9 * * 1` | Mondays at 09:00 |
| `0 8 * * 1-5` | weekdays at 08:00 |
| `@reboot` | once, when the Pi boots |

## Recipes

**Run a script every morning and keep a log:**

```
0 7 * * * /usr/bin/python3 /home/pi/raspberry-scripts/weather-script/weather_notify.py >> /home/pi/logs/weather.log 2>&1
```

**Queue a task at night inside tmux, review it in the morning.** This is the
tmux tie-in: cron starts a *detached session* at the given hour, the task runs
overnight, and next day you `tmux attach` to see exactly what happened:

```
0 22 * * * tmux new -d -s backup '/home/pi/scripts/backup.sh'
0 2 * * * tmux new -d -s claude 'cd /home/pi/myproject && claude -p "run the test suite and fix failures"'
```

**Bring docker up after every reboot / power cut:**

```
@reboot sleep 20 && tmux new -d -s docker 'cd /home/pi/myapp && docker compose up'
```

(the `sleep 20` gives the network and docker daemon time to start)

## Gotchas — read this before debugging

- **Use absolute paths for everything** — commands *and* files. Cron runs with
  almost no environment: no `~`, tiny `PATH`, no `.bashrc`. `python3 script.py`
  in your shell becomes `/usr/bin/python3 /home/pi/.../script.py` in cron.
- **Log the output or you'll fly blind.** End lines with
  `>> /home/pi/logs/task.log 2>&1`. Without it, output is silently discarded.
- **Check cron actually fired:**

  ```
  grep CRON /var/log/syslog | tail      # or: journalctl -u cron | tail
  ```

- **Timezone**: cron uses the Pi's clock — check it with `date`, fix with
  `sudo raspi-config` (Localisation).
- **Test the exact line manually first.** Paste the command part into your
  shell as-is. If it fails there, it will fail in cron too.

## When cron is not enough

Cron fires and forgets — if the task crashes, nothing restarts it. For a
service that must *always* be running (not just start at an hour), use a
systemd service with `Restart=on-failure` instead. Rule of thumb:
**cron = at a certain hour · tmux = while you're away · systemd = forever**.
