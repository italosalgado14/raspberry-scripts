# Server setup — Raspberry Pi 5

How to prepare a Raspberry Pi 5 as the host for this board: operating system,
Docker, and Tailscale with MagicDNS. This document is **only about the server**;
deploying the app itself (compose override, environment, first login) is the
second step and lives in the main [README](../README.md).

By the end of this guide the Pi is reachable from any of your devices — at home
or anywhere else — at a stable private name like `board.tail1234.ts.net`,
without opening a single port on your router.

---

## 0. Hardware & OS assumptions

- **Raspberry Pi 5** (any RAM size works for ~5 users).
- **Raspberry Pi OS Lite 64-bit** (Bookworm). The 64-bit image is required —
  the Docker images used here (`python:3.13-slim`, `node:22-alpine`,
  `caddy:2-alpine`) are multi-arch and run natively on ARM64.
- Flash with **Raspberry Pi Imager** and use its ⚙️ pre-configuration to set:
  hostname, your user + password, **enable SSH**, and Wi-Fi (if not using
  Ethernet). This gives you a headless Pi you can SSH into on first boot.
- Storage: a quality A2 microSD is fine; an NVMe/USB SSD is nicer (the app's
  SQLite database and attachments live on this disk).
- Prefer **Ethernet** over Wi-Fi for a server if you can.

All commands below run **on the Pi over SSH** unless stated otherwise.

```sh
ssh <your-user>@<pi-hostname-or-ip>.local
```

## 1. First boot: update the system

```sh
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Set the timezone (burndown snapshots are UTC-based, but correct local time
keeps logs sane):

```sh
sudo timedatectl set-timezone America/Santiago   # pick yours: timedatectl list-timezones
```

Optional but recommended for an always-on box — automatic security updates:

```sh
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades   # answer "Yes"
```

## 2. Install Docker

Use Docker's official convenience script (installs the engine + the
`docker compose` plugin, and enables the service on boot):

```sh
curl -fsSL https://get.docker.com | sh
```

Let your user run Docker without `sudo`:

```sh
sudo usermod -aG docker $USER
```

**Log out and SSH back in** (group changes only apply to new sessions), then
verify:

```sh
docker run --rm hello-world      # engine works
docker compose version           # compose plugin present
```

Nothing else to configure — the Docker service starts automatically on every
boot, and containers marked `restart: unless-stopped` (as this app's are) come
back by themselves after a reboot or power cut.

## 3. Install Tailscale and join your tailnet

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` prints an authentication URL
(`https://login.tailscale.com/a/...`). Open it in a browser on any device
where you're logged into your Tailscale account and approve the machine.

Verify:

```sh
tailscale status    # the Pi appears first, with a 100.x.y.z address
```

### Disable key expiry (important for a server!)

By default a Tailscale node's key **expires after ~180 days**, after which the
device silently drops off the tailnet until someone re-authenticates it — the
classic "the board stopped working" surprise months later. For a server,
disable it:

1. Open <https://login.tailscale.com/admin/machines>.
2. Find the Pi → **⋯** menu → **Disable key expiry**.

## 4. MagicDNS: a stable name for the Pi

MagicDNS gives every device in your tailnet a DNS name like
`<machine>.<tailnet>.ts.net`, so you use a name instead of a `100.x.y.z` IP.

1. Open <https://login.tailscale.com/admin/dns>.
2. Note your **tailnet name** at the top — e.g. `tail1234.ts.net` or a word
   pair like `velociraptor-alligator.ts.net`. It is the suffix of every
   device name.
3. In the **MagicDNS** section, make sure it is **enabled** (default on
   recent tailnets; enable the toggle if present).
4. (For later, same page) The **HTTPS Certificates** toggle lets Tailscale
   issue real Let's Encrypt certificates for `*.ts.net` names. Not needed for
   the basic deploy — the app ships with Caddy's internal CA — but enabling it
   now costs nothing and unlocks the warning-free TLS option later.

Give the Pi a clean machine name (this becomes the URL):

```sh
sudo tailscale set --hostname board
```

(or rename it in the admin console: **Machines** → the Pi → ⋯ → *Edit machine
name*).

Now read back the **exact full DNS name** — you will need it verbatim when
deploying the app:

```sh
tailscale status --json | grep '"DNSName"' | head -n1
#   "DNSName": "board.tail1234.ts.net.",
```

Your name is that value **without the trailing dot**: `board.tail1234.ts.net`.

### Verify from another device

On your laptop (with the Tailscale client installed and running):

```sh
ping board.tail1234.ts.net
```

- **At home**, Tailscale notices both devices share the LAN and connects them
  directly at local-network speed.
- **Anywhere else**, the same name works through an encrypted WireGuard
  tunnel. No port forwarding, no public exposure — only devices admitted to
  your tailnet can reach the Pi.

If the name doesn't resolve: re-check the MagicDNS toggle, then restart the
Tailscale client on the laptop.

## 5. Final checklist

| Check | Command (on the Pi) | Expect |
|---|---|---|
| Docker runs unprivileged | `docker run --rm hello-world` | "Hello from Docker!" |
| Compose plugin | `docker compose version` | a v2.x version |
| Tailscale is up | `tailscale status` | Pi listed with `100.x.y.z` |
| Key expiry disabled | admin console → Machines | "Expiry disabled" badge |
| MagicDNS name known | `tailscale status --json \| grep DNSName \| head -n1` | `board.<tailnet>.ts.net.` |
| Reachable from laptop | `ping board.<tailnet>.ts.net` (on the laptop) | replies |

## Next step: deploy the app

The server is ready. Continue with the app deployment — getting the repo onto
the Pi, the `docker-compose.override.yml` with your `.ts.net` name in
`CADDY_SITE_ADDRESS` / `DJANGO_CSRF_TRUSTED_ORIGINS`, a real
`DJANGO_SECRET_KEY`, and first login — described in the main
[README](../README.md).
