# Operations

`make run` starts the interactive terminal UI and also installs live Telegram sync. `make daemon` is for an unattended local process and should be supervised by the host process manager when used in production. No systemd unit is currently present in this repository.

If Telegram cannot connect after SQLite opens, `make run` continues in local-read
mode. It clearly disables Sync and analysis while retaining Search, Today,
Tasks, Ask, Review, and diagnostics. This is an interactive recovery path; an
unattended daemon still needs a healthy Telegram connection to perform useful
work.

Database safety: `data/telegram.sqlite` is a live WAL database. Use `make db-check` for read-only integrity checks and `make db-backup` for a consistent SQLite backup API snapshot. Never copy a live `.sqlite` file alone or inspect/commit Telegram session files.

`make health` only reports configuration presence; it never prints secrets.
