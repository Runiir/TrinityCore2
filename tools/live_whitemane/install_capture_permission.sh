#!/usr/bin/env bash
# One-time installation, run by Runiir with sudo. No account files are read.
set -euo pipefail
if (( EUID != 0 )); then
    echo 'Run this installer with sudo once.' >&2
    exit 1
fi
if (( $# != 0 )); then
    echo 'This installer accepts no arguments.' >&2
    exit 2
fi
/usr/bin/id runiir >/dev/null
for whitemane_parent in /usr /usr/local /usr/local/libexec /etc /etc/sudoers.d; do
    whitemane_uid=$(/usr/bin/stat -c '%u' "$whitemane_parent")
    whitemane_mode=$(/usr/bin/stat -c '%a' "$whitemane_parent")
    if [[ "$whitemane_uid" != 0 ]] || (( (8#$whitemane_mode & 022) != 0 )); then
        echo "Refusing a writable or non-root installation directory: $whitemane_parent" >&2
        exit 1
    fi
done
whitemane_temporary=$(/usr/bin/mktemp -d /usr/local/libexec/.whitemane-install.XXXXXX)
trap '/usr/bin/rm -rf -- "$whitemane_temporary"' EXIT
cat >"$whitemane_temporary/capture" <<'CAPTURE'
#!/bin/sh
set -eu
[ "$#" -eq 0 ] || { echo 'This capture accepts no arguments.' >&2; exit 2; }
# Fixed endpoint, non-promiscuous capture, stdout only. Drop root immediately
# after tcpdump opens the capture device. No caller-controlled paths or flags.
exec /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
    /usr/bin/tcpdump --immediate-mode -npi any -B 1024 -U -s 0 -w - \
    -Z runiir 'host 51.255.74.57 and tcp port 8085'
CAPTURE
cat >"$whitemane_temporary/sudoers" <<'SUDOERS'
# Only this root-owned, fixed-filter capture. Empty quotes prohibit arguments.
runiir ALL=(root) NOPASSWD: NOSETENV: /usr/local/libexec/whitemane-owned-capture ""
SUDOERS
/usr/sbin/visudo -cf "$whitemane_temporary/sudoers"
/usr/bin/install -o root -g root -m 0755 "$whitemane_temporary/capture" /usr/local/libexec/whitemane-owned-capture
/usr/bin/install -o root -g root -m 0440 "$whitemane_temporary/sudoers" /etc/sudoers.d/whitemane-owned-capture
if ! /usr/sbin/visudo -c; then
    /usr/bin/rm -f /etc/sudoers.d/whitemane-owned-capture
    echo 'Global sudoers validation failed; the new permission was removed.' >&2
    exit 1
fi
echo 'Installed fixed Whitemane capture permission for runiir. No general passwordless sudo granted.'
