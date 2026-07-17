# Raspberry Pi Storage Configuration — Checklist

This folder describes the expected configuration of the Raspberry Pi.

Goal: minimize writes to the SD card and keep all heavy disk activity (swap, databases, logs, script data) on the SSD.

Each section below has:
- **Check** — command(s) to evaluate the current state, and what a good result looks like.
- **Fix** — command(s) to apply if the check fails.

Run the checks on the Raspberry itself.

---

## 0. Identify the disks first

**Check:**
```bash
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL
```
Expected: you can identify which device is the SD (`mmcblk0`) and which is the SSD (`sda`, or `nvme0n1` on a Pi 5 with NVMe HAT). Note where `/` is mounted — that tells you if you boot from SD or SSD.

Also useful:
```bash
findmnt /          # what device the root filesystem is on
cat /proc/device-tree/model   # Pi model
```

---

## 1. (Preferred) Boot entirely from the SSD

If `/` is already on the SSD, sections 2–6 mostly become irrelevant: everything already lives on the SSD.

**Check:**
```bash
findmnt /
```
- Good: source is `/dev/sda2` or `/dev/nvme0n1p2` (SSD).
- Needs work: source is `/dev/mmcblk0p2` (SD).

**Fix (Pi 4/5):**
```bash
# 1. Update the bootloader
sudo apt update && sudo apt full-upgrade -y
sudo rpi-eeprom-update -a
sudo reboot

# 2. Set boot order (USB/NVMe first)
sudo raspi-config
# -> Advanced Options -> Boot Order -> USB Boot (or NVMe/USB Boot on Pi 5)

# 3. Flash Raspberry Pi OS to the SSD (from another machine with Raspberry Pi Imager),
#    or clone the running SD to the SSD:
sudo apt install rpi-clone   # or: git clone https://github.com/geerlingguy/rpi-clone
sudo rpi-clone sda           # replace sda with your SSD device

# 4. Shut down, (optionally) remove the SD, boot from SSD, re-run: findmnt /
```

If you boot from SSD, the rest of this file is optional hardening. If you stay on SD boot, sections 2–6 are required.

---

## 2. SSD mounted permanently with a stable fstab entry

**Check:**
```bash
findmnt /mnt/ssd
grep ssd /etc/fstab
```
- Good: SSD is mounted at `/mnt/ssd` (or your chosen mount point), fstab entry uses `UUID=` (not `/dev/sda1`, which can change) and includes `noatime`.
- Needs work: no entry, or entry uses `/dev/sdX` directly.

**Fix:**
```bash
# Get the UUID of the SSD partition
sudo blkid /dev/sda1

# Create the mount point
sudo mkdir -p /mnt/ssd

# Add to /etc/fstab (edit UUID accordingly)
echo 'UUID=xxxx-xxxx  /mnt/ssd  ext4  defaults,noatime,nofail  0  2' | sudo tee -a /etc/fstab

# Reload and mount (systemd needs the reload after editing fstab)
sudo systemctl daemon-reload
sudo mount -a

# Verify
findmnt /mnt/ssd
```
Note: `nofail` prevents the Pi from hanging at boot if the SSD is unplugged.

---

## 3. Swap: no swap on the SD (zram preferred)

**Check:**
```bash
swapon --show
free -h
```
- Good: swap devices are `/dev/zram0` only, or a file on the SSD (`/mnt/ssd/swap`).
- Needs work: `/var/swap` listed (that is the default dphys-swapfile on the SD).

**Fix — option A (preferred): zram, zero disk writes:**
```bash
# Remove the SD swap file
sudo dphys-swapfile swapoff
sudo systemctl disable --now dphys-swapfile
sudo rm -f /var/swap

# Install zram
sudo apt install -y zram-tools
# Optional: set size (percentage of RAM) in /etc/default/zramswap
sudo systemctl restart zramswap

# Verify
swapon --show   # should show /dev/zram0
```

**Fix — option B: swap file on the SSD:**
```bash
sudo sed -i 's|^#\?CONF_SWAPFILE=.*|CONF_SWAPFILE=/mnt/ssd/swap|' /etc/dphys-swapfile
sudo sed -i 's|^#\?CONF_SWAPSIZE=.*|CONF_SWAPSIZE=1024|' /etc/dphys-swapfile
sudo systemctl restart dphys-swapfile
swapon --show   # should show /mnt/ssd/swap
```

---

## 4. Logs: keep /var/log out of the SD (log2ram)

**Check:**
```bash
systemctl status log2ram --no-pager
df -h /var/log
```
- Good: log2ram active and `/var/log` mounted on `log2ram` (tmpfs).
- Needs work: log2ram not installed and `/var/log` sits on `/dev/mmcblk0p2`.

**Fix:**
```bash
echo "deb [signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] http://packages.azlux.fr/debian/ bookworm main" | sudo tee /etc/apt/sources.list.d/azlux.list
sudo wget -O /usr/share/keyrings/azlux-archive-keyring.gpg https://azlux.fr/repo.gpg
sudo apt update && sudo apt install -y log2ram
sudo reboot

# Verify after reboot
df -h /var/log   # filesystem should be log2ram
```

---

## 5. noatime on the SD root filesystem

Stops a write to the SD every time a file is merely read.

**Check:**
```bash
findmnt -o TARGET,OPTIONS /
```
- Good: options include `noatime`.
- Needs work: only `relatime` or neither.

**Fix:**
```bash
# Edit /etc/fstab: add noatime to the root (/) entry's options, e.g.
#   PARTUUID=xxxx-02  /  ext4  defaults,noatime  0  1
sudo nano /etc/fstab
sudo systemctl daemon-reload
sudo reboot   # or: sudo mount -o remount /
```

---

## 6. /tmp in RAM (tmpfs)

**Check:**
```bash
df -h /tmp
```
- Good: filesystem is `tmpfs`.
- Needs work: filesystem is the SD device.

**Fix:**
```bash
sudo systemctl enable /usr/share/systemd/tmp.mount
sudo reboot
# Or via fstab:
echo 'tmpfs  /tmp  tmpfs  defaults,noatime,nosuid,size=256m  0  0' | sudo tee -a /etc/fstab
```

---

## 7. Databases and script data on the SSD

**Check:**
```bash
# Find where your scripts write. For SQLite files:
find /home /var -name '*.db' -o -name '*.sqlite*' 2>/dev/null
# Confirm each path is on the SSD:
df -h <path-to-db>
```
- Good: all databases and frequently-written data live under `/mnt/ssd/...`.
- Needs work: DB files under `/home/pi` or `/var` while `/` is on the SD.

**Fix:**
```bash
sudo mkdir -p /mnt/ssd/data
# Move the data and point the scripts to the new path, or symlink:
mv /home/pi/mydata.db /mnt/ssd/data/
ln -s /mnt/ssd/data/mydata.db /home/pi/mydata.db
```
For a real database server (Postgres/MySQL), move its data directory to the SSD following that database's documented procedure instead of symlinking.

---

## 8. Monitor SD health over time

**Check:**
```bash
# Total writes per device since boot (sectors written = column 10 of /proc/diskstats)
awk '$3=="mmcblk0" || $3=="sda" {print $3, $10*512/1024/1024 " MB written since boot"}' /proc/diskstats

# Filesystem errors on the SD
sudo dmesg | grep -i -E 'mmc|error'
```
- Good: SD writes grow very slowly between reboots; no mmc errors in dmesg.
- Needs work: SD accumulating gigabytes of writes daily → something in sections 3–7 is misconfigured.

---

## Quick status summary (copy-paste)

```bash
echo '--- root device ---';      findmnt -o SOURCE,OPTIONS /
echo '--- ssd mount ---';        findmnt /mnt/ssd
echo '--- swap ---';             swapon --show
echo '--- /var/log ---';         df -h /var/log | tail -1
echo '--- /tmp ---';             df -h /tmp | tail -1
```
