#!/usr/bin/env bash
# Managed by metacube-rgb-dkms installer
set -Eeuo pipefail
PKG=metacube-ambient
VER=2.0.0
MODULE=metacube_ambient
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER='Managed by metacube-rgb-dkms installer'
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge-user-data) PURGE=1 ;;
    -h|--help) echo 'Usage: bash uninstall.sh [--purge-user-data]'; exit 0 ;;
    *) echo "Invalid option: $arg" >&2; exit 1 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
if [[ ! -d "/var/lib/dkms/$PKG/$VER" && ! -e /usr/local/lib/metacube-rgb/.managed ]]; then
  echo 'The v2 installation does not appear to exist; refusing to unload an unknown driver.' >&2
  exit 1
fi
systemctl disable --now metacube-rgb-web.service 2>/dev/null || true
systemctl disable --now metacube-rgb-restore.service 2>/dev/null || true
if [[ -e "/sys/module/$MODULE/version" ]]; then
  running="$(cat "/sys/module/$MODULE/version")"
  [[ "$running" == "$VER" ]] || { echo "Running module is $running, not $VER; will not unload." >&2; exit 1; }
  rmmod "$MODULE"
fi
if [[ -d "/var/lib/dkms/$PKG/$VER" ]]; then
  dkms remove -m "$PKG" -v "$VER" --all
fi
for file in \
  /usr/local/sbin/metacube-rgb \
  /etc/systemd/system/metacube-rgb-restore.service \
  /etc/systemd/system/metacube-rgb-web.service \
  /etc/modules-load.d/metacube-ambient.conf \
  /etc/modprobe.d/metacube-ambient.conf; do
  if [[ -f "$file" ]]; then
    if grep -Fq "$MARKER" "$file"; then rm -f -- "$file";
    else echo "Keeping unmanaged file: $file" >&2; fi
  fi
done
if [[ -f /usr/local/lib/metacube-rgb/.managed ]] && \
   grep -Fq "$MARKER" /usr/local/lib/metacube-rgb/.managed; then
  rm -rf -- /usr/local/lib/metacube-rgb
fi
SRC="/usr/src/${PKG}-${VER}"
if [[ -d "$SRC" ]] && cmp -s "$HERE/driver/dkms.conf" "$SRC/dkms.conf"; then
  for file in Makefile dkms.conf metacube_ambient.c; do
    if cmp -s "$HERE/driver/$file" "$SRC/$file"; then rm -f -- "$SRC/$file"; fi
  done
  rmdir "$SRC" 2>/dev/null || echo "Local edits preserved in $SRC"
fi
if [[ "$PURGE" == 1 ]]; then
  rm -f /etc/metacube-rgb.conf /etc/metacube-rgb/web.token /var/lib/metacube-rgb/presets.json
  rmdir /etc/metacube-rgb /var/lib/metacube-rgb 2>/dev/null || true
else
  echo 'Preserved Web authentication token, 5 presets and boot lighting configuration.'
fi
systemctl daemon-reload
depmod -a
printf 'Removed MetaCube v%s. PVE boot loader and MOK keys unchanged.\n' "$VER"
