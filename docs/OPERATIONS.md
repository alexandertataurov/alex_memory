# Operations

`make run` starts the interactive terminal UI and also installs live Telegram sync. `make daemon` is for an unattended local process and should be supervised by the host process manager when used in production.

If Telegram cannot connect after SQLite opens, `make run` continues in local-read
mode. It clearly disables Sync and analysis while retaining Search, Today,
Tasks, Ask, Review, and diagnostics. This is an interactive recovery path; an
unattended daemon still needs a healthy Telegram connection to perform useful
work.

Database safety: `data/telegram.sqlite` is a live WAL database. Use `make db-check` for read-only integrity checks and `make db-backup` for a consistent SQLite backup API snapshot. Never copy a live `.sqlite` file alone or inspect/commit Telegram session files.

`make health` only reports configuration presence; it never prints secrets.

## Optional systemd user supervision

Use this only on a host where the repository, virtual environment, and local
Telegram session are intentionally owned by the same user. Copy the template
to `~/.config/systemd/user/alex-memory.service`, replacing
`/path/to/alex_memory` with the absolute checkout path. Do not place secrets in
the unit: the process reads its existing local configuration file.

```ini
[Unit]
Description=Alex Memory local sync daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/alex_memory
ExecStart=/path/to/alex_memory/.venv/bin/python src/main.py --daemon
Restart=on-failure
RestartSec=30
TimeoutStopSec=30

[Install]
WantedBy=default.target
```

Before enabling it, run `make health` and `make db-check` from the same
checkout. Before any separate schema/repair operation, stop the unit and use
`make db-backup`; do not run a repair concurrently with the daemon. Enable it
only after review with `systemctl --user daemon-reload` and
`systemctl --user enable --now alex-memory.service`. Inspect failures with
`systemctl --user status alex-memory.service`; the 30-second restart delay
prevents a tight crash loop.
