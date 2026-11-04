#!/usr/bin/env bash
# Managed by metacube-rgb-dkms installer
set -Eeuo pipefail

PKG='metacube-ambient'
VER='2.3.0'
OLD='1.0.0'  # detected below: v1, v2.0 or v2.1 predecessor
MODULE='metacube_ambient'
GUID='B60BFB48-3E5B-49E4-A0E9-8CFFE1B3434B'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="/usr/src/${PKG}-${VER}"
KERNEL="$(uname -r)"
WMI="/sys/bus/wmi/devices/${GUID}"
CLI='/usr/local/sbin/metacube-rgb'
LIBROOT='/usr/local/lib/metacube-rgb'
UNIT='/etc/systemd/system/metacube-rgb-restore.service'
WEBUNIT='/etc/systemd/system/metacube-rgb-web.service'
MODULES_CONF='/etc/modules-load.d/metacube-ambient.conf'
MODPROBE_CONF='/etc/modprobe.d/metacube-ambient.conf'
MARKER='Managed by metacube-rgb-dkms installer'
WRITES=''
PLATFORM=0
RESTORE=0
WEB_ONLY=0
OLD_INSTALLED=0
OLD_REMOVED=0
WEB_RUNNING=0
MODULE_SWITCHED=0
ORIGINAL_LOADED=0
UPGRADE_COMMITTED=0
TARGET_NEW=0
SRC_NEW=0
SNAPSHOT=''

fail(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info(){ printf '[metacube-rgb] %s\n' "$*"; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "Missing tool: $1"; }
usage(){
  cat <<'TXT'
Usage: bash install.sh [--enable-writes | --disable-writes]
                       [--enable-platform-writes] [--enable-restore]
       bash install.sh --web-only
  --enable-writes          Allow RGB writes. Omitted => preserve current policy.
  --disable-writes         Force all firmware writes off.
  --enable-platform-writes ALSO enable OEM performance/keyboard button writes.
                           AC online required for Turbo; not tested on this PVE.
  --enable-restore         Enable boot light restoration, saving initial preset
                           only when not already present.
  --web-only               Update Web/CLI files only; no DKMS or kernel changes.
  No web listener is enabled automatically; start 'metacube-rgb web'.
TXT
}
mok_is_enrolled(){
  local output status=0
  output="$(LC_ALL=C mokutil --test-key /var/lib/dkms/mok.pub 2>&1)" || status=$?
  [[ "$output" == *"is already enrolled"* ]] && return 0
  [[ "$status" -eq 0 && "$output" != *"not enrolled"* ]] && return 0
  printf 'MOK key test (exit %s): %s\n' "$status" "$output" >&2
  return 1
}
check_managed(){
  local target="$1"
  if [[ -e "$target" ]] && ! grep -Fq "$MARKER" "$target"; then
    fail "Refusing to replace unmanaged file: $target"
  fi
}
managed_paths=("$CLI" "$UNIT" "$WEBUNIT" "$MODULES_CONF" "$MODPROBE_CONF" "$LIBROOT")
snapshot_managed_paths(){
  local idx item
  SNAPSHOT="$(mktemp -d /tmp/metacube-rgb-rollback.XXXXXX)"
  chmod 0700 "$SNAPSHOT"
  for idx in "${!managed_paths[@]}"; do
    item="${managed_paths[$idx]}"
    if [[ -e "$item" ]]; then
      cp -a -- "$item" "$SNAPSHOT/$idx"
      : > "$SNAPSHOT/$idx.present"
    fi
  done
  if [[ -d "/sys/module/$MODULE" ]]; then ORIGINAL_LOADED=1; fi
}
restore_managed_paths(){
  local idx item
  [[ -n "$SNAPSHOT" && -d "$SNAPSHOT" ]] || return 0
  for idx in "${!managed_paths[@]}"; do
    item="${managed_paths[$idx]}"
    if [[ -f "$SNAPSHOT/$idx.present" ]]; then
      rm -rf -- "$item"
      cp -a -- "$SNAPSHOT/$idx" "$item"
    else
      rm -rf -- "$item"
    fi
  done
  systemctl daemon-reload 2>/dev/null || true
}
rollback_on_exit(){
  local rc="$1" running
  trap - EXIT
  if [[ "$rc" -ne 0 && "$UPGRADE_COMMITTED" -ne 1 && -n "$SNAPSHOT" ]]; then
    if [[ "$WEB_ONLY" -eq 1 ]]; then
      printf 'Web-only update failed. Restoring the installed Web files...\n' >&2
      restore_managed_paths
      if [[ "$WEB_RUNNING" -eq 1 ]]; then
        systemctl start metacube-rgb-web.service 2>&1 || true
      fi
      rm -rf -- "$SNAPSHOT"
      exit "$rc"
    fi
    printf 'Upgrade failed. Attempting to restore the pre-upgrade configuration...\n' >&2
    systemctl stop metacube-rgb-web.service 2>/dev/null || true
    if [[ -d "/sys/module/$MODULE" ]]; then
      running="$(cat "/sys/module/$MODULE/version" 2>/dev/null || true)"
      if [[ "$running" == "$VER" ]]; then rmmod "$MODULE" 2>&1 || true; fi
    fi
    if [[ -d "/var/lib/dkms/$PKG/$VER" ]]; then
      if [[ "$TARGET_NEW" -eq 1 ]]; then
        # Do not leave a failed v2 AUTOINSTALL registration behind.
        dkms remove -m "$PKG" -v "$VER" --all 2>&1 || true
      else
        dkms uninstall -m "$PKG" -v "$VER" -k "$KERNEL" 2>&1 || true
      fi
    fi
    if [[ "$OLD_REMOVED" -eq 1 && -d "/var/lib/dkms/$PKG/$OLD" ]]; then
      dkms install -m "$PKG" -v "$OLD" -k "$KERNEL" 2>&1 || true
    fi
    depmod -a "$KERNEL" 2>&1 || true
    restore_managed_paths
    if [[ "$SRC_NEW" -eq 1 && -d "$SRC" ]] &&
       [[ ! -d "/var/lib/dkms/$PKG/$VER" ]]; then
      for file in metacube_ambient.c Makefile dkms.conf; do
        if cmp -s "$HERE/driver/$file" "$SRC/$file"; then rm -f -- "$SRC/$file"; fi
      done
      rmdir "$SRC" 2>/dev/null || true
    fi
    if [[ "$ORIGINAL_LOADED" -eq 1 && ! -d "/sys/module/$MODULE" ]]; then
      modprobe "$MODULE" 2>&1 || true
    fi
    if [[ "$WEB_RUNNING" -eq 1 ]]; then
      systemctl start metacube-rgb-web.service 2>&1 || true
    fi
    printf 'Verify DKMS status and the running module before retrying.\n' >&2
  fi
  if [[ -n "$SNAPSHOT" ]]; then rm -rf -- "$SNAPSHOT"; fi
  exit "$rc"
}
trap 'rollback_on_exit $?' EXIT

for arg in "$@"; do
  case "$arg" in
    --enable-writes) WRITES=1 ;;
    --disable-writes) WRITES=0 ;;
    --enable-platform-writes) PLATFORM=1; WRITES=1 ;;
    --enable-restore) RESTORE=1; WRITES=1 ;;
    --web-only) WEB_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "Unknown argument: $arg" ;;
  esac
done
[[ $EUID -eq 0 ]] || fail 'Must run as root on the PVE host.'
if [[ "$WEB_ONLY" -eq 1 ]]; then
  [[ -z "$WRITES" && "$PLATFORM" -eq 0 && "$RESTORE" -eq 0 ]] || fail '--web-only cannot be combined with driver options'
  [[ -f "$LIBROOT/.managed" && -f "$CLI" ]] || fail 'Existing MetaCube installation not found'
  grep -Fq "$MARKER" "$CLI" || fail 'Unmanaged CLI; refusing to update'
  [[ -d "$LIBROOT/python/metacube_rgb" && -d "$LIBROOT/python/web" ]] || fail 'Existing Web assets not found'
  need python3
  need systemctl
  python3 -m py_compile "$HERE/metacube_rgb/cli.py" "$HERE/metacube_rgb/web.py" "$HERE/metacube_rgb/webctl.py" "$HERE/metacube_rgb/__init__.py" || fail 'Python syntax check failed'
  snapshot_managed_paths
  if systemctl is-active --quiet metacube-rgb-web.service 2>/dev/null; then
    WEB_RUNNING=1
    systemctl stop metacube-rgb-web.service
  fi
  info 'Updating Web/CLI files without touching the DKMS module'
  for file in "$HERE"/metacube_rgb/*.py; do install -m 0644 "$file" "$LIBROOT/python/metacube_rgb/$(basename "$file")"; done
  install -m 0644 "$HERE/metacube_rgb/system_templates.json" "$LIBROOT/python/metacube_rgb/system_templates.json"
  for file in "$HERE"/web/*; do install -m 0644 "$file" "$LIBROOT/python/web/$(basename "$file")"; done
  "$CLI" web --help >/dev/null
  if [[ "$WEB_RUNNING" -eq 1 ]]; then systemctl start metacube-rgb-web.service; fi
  UPGRADE_COMMITTED=1
  info 'Web-only update complete. Driver version and signing unchanged.'
  info 'Manual Web sessions must be restarted to use the new defaults.'
  exit 0
fi
[[ "$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)" == 'METAPHYUNI' ]] || fail 'Unexpected vendor; refusing to run.'
[[ "$(cat /sys/class/dmi/id/product_name 2>/dev/null)" == 'MetaCube' ]] || fail 'Unexpected product; refusing to run.'
[[ "$(cat /sys/class/dmi/id/board_name 2>/dev/null)" == 'M11 Series-HPT' ]] || fail 'Only M11 Series-HPT is currently supported.'
[[ -d "$WMI" ]] || fail "Missing target WMI GUID: $GUID"
[[ -d "/lib/modules/${KERNEL}/build" ]] || fail "Missing kernel headers: apt install proxmox-headers-${KERNEL}"
for cmd in python3 dkms make gcc modprobe modinfo depmod rmmod install systemctl grep; do need "$cmd"; done
if [[ -L "$WMI/driver" ]]; then
  bound="$(basename "$(readlink -f "$WMI/driver")")"
  [[ "$bound" == "$MODULE" ]] || fail "WMI already bound to another driver: $bound"
fi
if command -v mokutil >/dev/null 2>&1 && mokutil --sb-state 2>/dev/null | grep -qi 'secureboot enabled'; then
  [[ -s /var/lib/dkms/mok.key && -s /var/lib/dkms/mok.pub ]] || fail 'Secure Boot MOK keypair missing; will not replace existing enrolled keys.'
  mok_is_enrolled || fail 'DKMS MOK public key is not enrolled; refused before build.'
fi
for target in "$CLI" "$UNIT" "$WEBUNIT" "$MODULES_CONF" "$MODPROBE_CONF"; do check_managed "$target"; done
if [[ -e "$LIBROOT" && ! -e "$LIBROOT/.managed" ]]; then fail "Refusing to overwrite unmanaged directory $LIBROOT"; fi
if [[ -d "$SRC" ]]; then
  for file in metacube_ambient.c Makefile dkms.conf; do
    cmp -s "$HERE/driver/$file" "$SRC/$file" || fail "Existing $SRC/$file differs from this release"
  done
fi
if [[ -z "$WRITES" ]]; then
  if [[ -f "$MODPROBE_CONF" ]] && grep -q 'allow_writes=1' "$MODPROBE_CONF"; then WRITES=1; else WRITES=0; fi
fi
if [[ "$WRITES" -eq 0 && "$PLATFORM" -eq 1 ]]; then fail 'Platform writes also require --enable-writes'; fi

# Select the previously installed module, if any. Do not remove a wrong version
# when the host has both v1 and v2 source registrations.
for candidate in 2.2.0 2.1.0 2.0.0 1.0.0; do
  if [[ "$(dkms status -m "$PKG" -v "$candidate" -k "$KERNEL" 2>/dev/null || true)" == *': installed'* ]]; then
    OLD="$candidate"
    break
  fi
done
snapshot_managed_paths
info "Preparing DKMS v$VER; build occurs before touching the running module"
if [[ ! -d "$SRC" ]]; then
  SRC_NEW=1
  install -d -m 0755 "$SRC"
  for file in metacube_ambient.c Makefile dkms.conf; do install -m 0644 "$HERE/driver/$file" "$SRC/$file"; done
fi
if [[ ! -e "/var/lib/dkms/$PKG/$VER/source" ]]; then
  TARGET_NEW=1
  dkms add -m "$PKG" -v "$VER"
fi
new_status="$(dkms status -m "$PKG" -v "$VER" -k "$KERNEL" 2>/dev/null || true)"
if [[ "$new_status" != *': built'* && "$new_status" != *': installed'* ]]; then
  dkms build -m "$PKG" -v "$VER" -k "$KERNEL"
fi
info 'DKMS build passed'
old_status="$(dkms status -m "$PKG" -v "$OLD" -k "$KERNEL" 2>/dev/null || true)"
if [[ "$old_status" == *': installed'* ]]; then
  OLD_INSTALLED=1
  info "Uninstalling previous DKMS $OLD for the current kernel (source retained for rollback)"
  dkms uninstall -m "$PKG" -v "$OLD" -k "$KERNEL"
  OLD_REMOVED=1
fi
new_status="$(dkms status -m "$PKG" -v "$VER" -k "$KERNEL" 2>/dev/null || true)"
if [[ "$new_status" != *': installed'* ]]; then dkms install -m "$PKG" -v "$VER" -k "$KERNEL"; fi
depmod -a "$KERNEL"
[[ "$(modinfo -F version "$MODULE")" == "$VER" ]] || fail 'Installed module version mismatch'
[[ "$(modinfo -F filename "$MODULE")" == *'/updates/dkms/'* ]] || fail 'Module not found in DKMS module directory'
if command -v mokutil >/dev/null 2>&1 && mokutil --sb-state 2>/dev/null | grep -qi 'secureboot enabled'; then
  [[ -n "$(modinfo -F signer "$MODULE")" ]] || fail 'DKMS module signature missing'
fi

if systemctl is-active --quiet metacube-rgb-web.service 2>/dev/null; then
  WEB_RUNNING=1
  systemctl stop metacube-rgb-web.service
fi
info 'Installing controller, static web assets and services'
install -d -m 0755 "$LIBROOT/python/metacube_rgb" "$LIBROOT/python/web"
for file in "$HERE"/metacube_rgb/*.py; do install -m 0644 "$file" "$LIBROOT/python/metacube_rgb/$(basename "$file")"; done
install -m 0644 "$HERE/metacube_rgb/system_templates.json" "$LIBROOT/python/metacube_rgb/system_templates.json"
for file in "$HERE"/web/*; do install -m 0644 "$file" "$LIBROOT/python/web/$(basename "$file")"; done
printf '%s\n' "$MARKER" > "$LIBROOT/.managed"
install -m 0755 "$HERE/tools/metacube-rgb" "$CLI"
install -m 0644 "$HERE/systemd/metacube-rgb-restore.service" "$UNIT"
install -m 0644 "$HERE/systemd/metacube-rgb-web.service" "$WEBUNIT"
printf '# %s\n%s\n' "$MARKER" "$MODULE" > "$MODULES_CONF"
printf '# %s\noptions %s allow_writes=%s allow_platform_writes=%s\n' "$MARKER" "$MODULE" "$WRITES" "$PLATFORM" > "$MODPROBE_CONF"
install -d -m 0700 /etc/metacube-rgb /var/lib/metacube-rgb
if [[ ! -e /etc/metacube-rgb/web.token ]]; then
  (umask 077; python3 -c 'import pathlib,secrets; f=pathlib.Path("/etc/metacube-rgb/web.token"); f.write_text(secrets.token_urlsafe(36)+"\n")')
  chmod 0600 /etc/metacube-rgb/web.token
fi
[[ "$(stat -c '%a' /etc/metacube-rgb/web.token)" == '600' ]] || fail 'Web token must be chmod 600'
systemctl daemon-reload

if [[ -d "/sys/module/$MODULE" ]]; then
  info 'Unloading the current module for seamless v2 switch'
  rmmod "$MODULE" || fail 'Unable to unload old module; aborting activation'
fi
modprobe "$MODULE" || fail 'Unable to load signed v2 module'
[[ -r "$WMI/ambient_raw" && -r "$WMI/ambient_apply" && -r "$WMI/oem_fan_rpm_oem" ]] || fail 'Expected RGB and OEM fan-monitor sysfs attributes were not created'
[[ "$(cat /sys/module/$MODULE/parameters/allow_writes)" == "$([[ "$WRITES" == '1' ]] && echo Y || echo N)" ]] || fail 'RGB write flag mismatch'
[[ "$(cat /sys/module/$MODULE/parameters/allow_platform_writes)" == "$([[ "$PLATFORM" == '1' ]] && echo Y || echo N)" ]] || fail 'Platform write flag mismatch'
MODULE_SWITCHED=1

UPGRADE_COMMITTED=1

# Remove v1 DKMS registration to prevent two versions targeting the same
# module on a future kernel. Retain /usr/src/metacube-ambient-1.0.0 as backup.
if [[ -d "/var/lib/dkms/$PKG/$OLD" ]]; then
  info "Removing previous DKMS registration $OLD (source retained)"
  dkms remove -m "$PKG" -v "$OLD" --all || info 'Warning: predecessor DKMS registry clean-up did not complete'
fi
if [[ "$RESTORE" == 1 ]]; then
  if [[ ! -e /etc/metacube-rgb.conf ]]; then "$CLI" save; fi
  systemctl enable --now metacube-rgb-restore.service
fi
if [[ "$WEB_RUNNING" == 1 ]]; then systemctl start metacube-rgb-web.service; fi
"$CLI" status
info "Installed v$VER. CLI: metacube-rgb web"
info 'Web defaults to 0.0.0.0:8765 (LAN access); restrict access using host firewall.'
info 'Use --host <LAN-IP> to limit the listener to a single network interface.'
info 'Web token file: /etc/metacube-rgb/web.token (owner-only)'
info 'No firmware writes performed during installation.'
