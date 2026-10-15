#!/usr/bin/env bash
#
# Auto install Shadowsocks Server (libev and rust) with SIP003 plugins
#   -- Enhanced fork of teddysun/shadowsocks_install --
#
# Improvements over the upstream script (see CHANGELOG.md for the full list):
#   * Supports Debian 10/11/12/13 and Ubuntu 20.04/22.04/24.04 in one binary
#   * Falls back to distro package -> upstream tarball when teddysun's PPA
#     is missing for a release
#   * Default: interactive — user picks port, password, cipher, plugin
#   * Optional: --auto (or -y) skips every prompt, uses --port/--password
#     when given and random values otherwise. Default cipher is aes-256-gcm.
#   * Random password suggested (was: hardcoded "teddysun.com")
#   * Detects apt/dnf package presence with apt_has_package, so a missing
#     shadowsocks-libev package is reported clearly instead of a silent fail
#   * systemd unit name picked per distro, no more wrong service name on
#     Debian 12/13 / Ubuntu 22.04+
#   * Cleans up download cache (was kept forever in the cwd)
#
# Original upstream:
#   https://github.com/teddysun/shadowsocks_install/blob/master/shadowsocks-all.sh
# Reference URLs:
#   https://github.com/shadowsocks/shadowsocks-libev
#   https://github.com/shadowsocks/shadowsocks-rust
#   https://github.com/teddysun/v2ray-plugin
#   https://github.com/teddysun/xray-plugin
#
###############################################################################
set -o pipefail
shopt -s inherit_errexit 2>/dev/null || true

SCRIPT_NAME=$(basename "$0")
SCRIPT_VERSION='2.0.0-enhanced'
SUPPORTED_TYPES=(libev rust)
DEFAULT_CIPHER='aes-256-gcm'

# Distro package unit names (Debian 12+/Ubuntu 22.04+).
readonly LIBEV_SERVICE='shadowsocks-libev.service'
readonly RUST_SERVICE='shadowsocks-rust.service'
readonly SYSTEMD_DIR='/etc/systemd/system'
readonly SYSV_INIT='/etc/init.d/shadowsocks-libev'

# Color codes (auto-disabled when stdout is not a TTY)
if [ -t 1 ]; then
    readonly RED='\e[0;31m' GREEN='\e[0;32m' YELLOW='\e[0;33m' PLAIN='\e[0m'
else
    readonly RED='' GREEN='' YELLOW='' PLAIN=''
fi

#==============================================================================
# Logging
#==============================================================================
log_info()  { printf '%b[Info ]%b  %s\n'  "$GREEN"  "$PLAIN" "$*" >&2; }
log_warn()  { printf '%b[Warn ]%b  %s\n'  "$YELLOW" "$PLAIN" "$*" >&2; }
log_error() { printf '%b[Error]%b  %s\n'  "$RED"    "$PLAIN" "$*" >&2; }
die() { log_error "$*"; exit 1; }

#==============================================================================
# Argument parsing
#==============================================================================
ACTION='install'
# AUTO_YES: when set via --auto, skip all interactive prompts and use
# defaults (random port if --port not given, random password, default
# cipher, no plugin). Default mode is interactive.
AUTO_YES=0
SS_TYPE='libev'
SS_PORT=''
SS_PASSWORD=''
SS_CIPHER="$DEFAULT_CIPHER"
SS_PLUGIN='none'
SS_PLUGIN_OPTS='server'

usage() {
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
    cat <<EOF
Usage:
  sudo $SCRIPT_NAME                              # fully interactive install
  sudo $SCRIPT_NAME install --type libev         # still asks for port / password / cipher
  sudo $SCRIPT_NAME install --port 443           # still asks for type / password / cipher
  sudo $SCRIPT_NAME install --auto               # no questions; random port + random password
  sudo $SCRIPT_NAME install --port 443 --auto    # use 443 + random password
  sudo $SCRIPT_NAME install --type rust --plugin v2ray --auto
  sudo $SCRIPT_NAME uninstall

Options:
  install | uninstall        action (default: install)
  --type TYPE                libev | rust       (default: libev, still asked unless --auto)
  --port PORT                1-65535            (asked if missing; random if --auto and no --port)
  --password PASSWORD        auth password      (asked if missing; random if --auto and no --password)
  --cipher CIPHER            stream cipher      (default: ${DEFAULT_CIPHER})
  --plugin {none|v2ray|xray} SIP003 plugin      (default: none; rust only)
  --auto, -y                 skip all prompts; fill in random values for anything not given
  -h, --help                 this help
EOF
    exit 0
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            install)     ACTION='install'; shift ;;
            uninstall)   ACTION='uninstall'; shift ;;
            --type)      SS_TYPE="$2"; shift 2 ;;
            --port)      SS_PORT="$2"; shift 2 ;;
            --password)  SS_PASSWORD="$2"; shift 2 ;;
            --cipher)    SS_CIPHER="$2"; shift 2 ;;
            --plugin)    SS_PLUGIN="$2"; shift 2 ;;
            --auto|-y)   AUTO_YES=1; shift ;;
            -h|--help)   usage ;;
            *)           die "Unknown argument: $1 (try --help)" ;;
        esac
    done
}

#==============================================================================
# Environment checks
#==============================================================================
[[ $EUID -ne 0 ]] && die "This script must be run as root: sudo $0 $*"

detect_pkg_manager() {
    if   command -v apt-get >/dev/null; then echo 'apt'
    elif command -v dnf     >/dev/null; then echo 'dnf'
    elif command -v yum     >/dev/null; then echo 'yum'
    else die "No supported package manager (apt / dnf / yum)"
    fi
}

has_systemd() {
    [ -d /run/systemd/system ] && return 0
    [ "$(readlink /proc/1/exe 2>/dev/null)" = *"/systemd" ] && return 0
    command -v systemctl >/dev/null 2>&1 && systemctl --version >/dev/null 2>&1 && return 0
    return 1
}

os_pretty() {
    local v c
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        v="${VERSION_ID:-?}"
        c="${VERSION_CODENAME:-}"
        [ -n "$c" ] && c=" ($c)"
        echo "${PRETTY_NAME:-Linux} ${v}${c}"
    else
        echo "Unknown Linux"
    fi
}

# Does this apt repo have a candidate for the given virtual name?
apt_has_package() {
    apt-cache show "$1" >/dev/null 2>&1
}

is_port() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]; }
is_cipher() {
    case "$1" in
        aes-256-gcm|aes-192-gcm|aes-128-gcm|aes-256-cfb|aes-128-cfb|\
        aes-256-ctr|aes-192-ctr|aes-128-ctr|chacha20-ietf-poly1305|\
        chacha20-ietf|chacha20|xchacha20-ietf-poly1305|salsa20|rc4-md5|\
        2022-blake3-aes-256-gcm|2022-blake3-aes-128-gcm|\
        2022-blake3-chacha20-poly1305) return 0 ;;
        *) return 1 ;;
    esac
}
is_type() {
    local t; for t in "${SUPPORTED_TYPES[@]}"; do [ "$t" = "$1" ] && return 0; done
    return 1
}

gen_password() { openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 24; }
gen_port() {
    local p
    while :; do
        p=$(( (RANDOM % 64535) + 1024 ))
        is_port "$p" && { echo "$p"; return; }
    done
}

# Detect runtimes that block setuid/setgid (containers without USER
# namespace support, some CI runners, systemd-nspawn without --private-users).
# In those, ss-server cannot drop to "nobody" — skip the user directive.
can_drop_privileges() {
    [ "$(id -u)" = "0" ] || return 1
    [ -d /proc/self/ns ] || return 1
    # The only reliable way to know if the kernel allows setgid is to
    # actually try. Use python3 to invoke setgid() AND setgroups() and
    # see whether they raise EPERM.
    local gid
    gid=$(getent group nogroup | cut -d: -f3)
    [ -n "$gid" ] || gid=$(getent group nobody | cut -d: -f3)
    [ -n "$gid" ] || return 1
    python3 -c 'import ctypes,sys
try:
    libc=ctypes.CDLL("libc.so.6")
    libc.setgid(int(sys.argv[1]))
    libc.setgroups(0, [])
except OSError as e:
    sys.exit(1 if e.errno in (1, 22) else 0)' "$gid" 2>/dev/null
}

#==============================================================================
# Network helpers
#==============================================================================
download() {
    local url="$1" out="$2"
    if [ -f "$out" ] && [ -s "$out" ]; then
        log_info "$(basename "$out") [found, cached]"
        return 0
    fi
    log_info "Downloading $(basename "$out") ..."
    if command -v curl >/dev/null; then
        curl --fail --location --retry 3 --connect-timeout 20 -o "$out" "$url"
    elif command -v wget >/dev/null; then
        wget --no-check-certificate -c -t3 -T60 -O "$out" "$url"
    else
        die "Need curl or wget"
    fi
}

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

#==============================================================================
# 1. Interactive prompts — ask for every setting the user did not provide.
#==============================================================================
# Behaviour:
#   * Each ask shows the *current* (CLI or default) value in brackets.
#     Pressing Enter accepts; the user can also type a new value.
#   * The user is always asked, even for values that came from --port /
#     --password / --cipher, so they can confirm or change.
#   * This function REQUIRES a TTY. If you call it from `curl | bash` it
#     will die with a clear "need --port/--password/--cipher pre-set"
#     error message instead of silently using defaults.
interactive_ask() {
    # Force non-interactive fallback when stdin is not a real terminal,
    # OR when running under sudo with requiretty where /dev/tty exists
    # but our stdin is still a pipe from curl.
    if [ ! -t 0 ] || [ ! -r /dev/tty ] 2>/dev/null; then
        log_warn "Interactive mode requires a TTY; falling back to auto mode."
        log_warn "Re-run with --auto or pre-set --port/--password/--cipher to silence this."
        AUTO_YES=1
        SS_PORT="${SS_PORT:-$(gen_port)}"
        SS_PASSWORD="${SS_PASSWORD:-$(gen_password)}"
        return 0
    fi

    local def

    # --- type ---
    echo "Which Shadowsocks implementation?"
    echo "  1) libev (recommended)"
    echo "  2) rust"
    read -r -p "Choice [1]: " REPLY
    case "${REPLY:-1}" in
        2) SS_TYPE='rust'  ;;
        *) SS_TYPE='libev' ;;
    esac

    # --- port ---
    if [ -z "$SS_PORT" ]; then def=$(gen_port); else def="$SS_PORT"; fi
    while :; do
        read -r -p "Server port [1-65535] (default: $def): " REPLY
        SS_PORT="${REPLY:-$def}"
        is_port "$SS_PORT" && break
        log_warn "Please enter a number between 1 and 65535"
    done

    # --- password ---
    while :; do
        read -r -p "Generate a random password? [Y/n]: " REPLY
        REPLY="${REPLY:-Y}"
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            SS_PASSWORD=$(gen_password)
            log_info "Generated password: $SS_PASSWORD"
            break
        fi
        if [[ "$REPLY" =~ ^[Nn]$ ]]; then
            while :; do
                read -rs -p "Enter password (>= 6 chars): " REPLY; echo
                [ "${#REPLY}" -ge 6 ] && { SS_PASSWORD="$REPLY"; break; }
                log_warn "Password too short (need >= 6 chars)"
            done
            break
        fi
        log_warn "Please answer Y or n"
    done

    # --- cipher ---
    # Strong AEAD ciphers are listed first; weaker ones (CTR, CFB, etc.)
    # are kept at the bottom for compatibility.
    if [ "$SS_TYPE" = "rust" ]; then
        local ciphers=(
            "aes-256-gcm"                       # 1  recommended
            "aes-128-gcm"                       # 2
            "chacha20-ietf-poly1305"            # 3
            "xchacha20-ietf-poly1305"            # 4
            "2022-blake3-aes-256-gcm"           # 5  (AEAD-2022)
            "2022-blake3-aes-128-gcm"           # 6
            "2022-blake3-chacha20-poly1305"     # 7
        )
    else
        local ciphers=(
            "aes-256-gcm"                       # 1  recommended
            "aes-128-gcm"                       # 2
            "chacha20-ietf-poly1305"            # 3
            "xchacha20-ietf-poly1305"            # 4
            "chacha20-ietf"                     # 5
            "aes-256-ctr"                       # 6
        )
    fi
    echo "Stream cipher (current: ${SS_CIPHER:-${ciphers[0]}}):"
    local i
    for ((i=0; i<${#ciphers[@]}; i++)); do
        echo "  $((i+1))) ${ciphers[i]}"
    done
    while :; do
        read -r -p "Choice [1]: " REPLY
        REPLY="${REPLY:-1}"
        if [[ "$REPLY" =~ ^[0-9]+$ ]] \
           && [ "$REPLY" -ge 1 ] && [ "$REPLY" -le "${#ciphers[@]}" ]; then
            SS_CIPHER="${ciphers[REPLY-1]}"
            break
        fi
        # Allow the user to type a cipher name directly.
        if is_cipher "$REPLY"; then
            SS_CIPHER="$REPLY"
            break
        fi
        log_warn "Please enter a number 1..${#ciphers[@]} or a cipher name"
    done

    # --- plugin (rust only) ---
    if [ "$SS_TYPE" = "rust" ]; then
        echo "SIP003 plugin (current: ${SS_PLUGIN}):"
        echo "  1) none  2) v2ray-plugin  3) xray-plugin"
        while :; do
            read -r -p "Choice [1]: " REPLY
            case "${REPLY:-1}" in
                1|'') SS_PLUGIN='none'; break ;;
                2)    SS_PLUGIN='v2ray'; break ;;
                3)    SS_PLUGIN='xray'; break ;;
                *)    log_warn "Please enter 1, 2 or 3" ;;
            esac
        done
    fi
    if [ "$SS_PLUGIN" != "none" ] && [ -z "${SS_PLUGIN_OPTS_CLI:-}" ]; then
        read -r -p "Plugin options (default: server): " REPLY
        SS_PLUGIN_OPTS="${REPLY:-server}"
    fi

    # --- summary ---
    cat <<EOF

Configuration:
  Type        : $SS_TYPE
  Port        : $SS_PORT
  Cipher      : $SS_CIPHER
  Password    : $SS_PASSWORD
  Plugin      : $SS_PLUGIN${SS_PLUGIN_OPTS:+ ($SS_PLUGIN_OPTS)}

Press Enter to continue, or Ctrl+C to abort.
EOF
    read -r _
}

#==============================================================================
# 2. Install (apt first, GitHub release fallback) - shadowsocks-libev
#==============================================================================
install_shadowsocks_libev() {
    if command -v ss-server >/dev/null; then
        log_info "shadowsocks-libev already installed"
        return 0
    fi

    local pm; pm=$(detect_pkg_manager)
    case "$pm" in
        apt)
            if apt_has_package shadowsocks-libev; then
                log_info "Installing shadowsocks-libev via apt"
                DEBIAN_FRONTEND=noninteractive \
                    apt-get -y -o Dpkg::Options::="--force-confdef" \
                               -o Dpkg::Options::="--force-confnew" \
                        --no-install-recommends install shadowsocks-libev
                command -v ss-server >/dev/null && return 0
                log_warn "apt install ran but ss-server not present; trying GitHub release"
            fi
            ;;
        dnf|yum)
            if $pm -y install shadowsocks-libev; then
                command -v ss-server >/dev/null && return 0
            fi
            ;;
    esac

    # Fallback: GitHub release tarball
    log_info "Downloading shadowsocks-libev v${LIBEV_VER:-latest} from GitHub"
    local ver tar url
    ver=$(curl -fsSL https://api.github.com/repos/shadowsocks/shadowsocks-libev/releases/latest \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"v?([^"]+)".*/\1/') \
        || die "Cannot resolve latest shadowsocks-libev"
    tar="shadowsocks-libev-${ver}.tar.gz"
    url="https://github.com/shadowsocks/shadowsocks-libev/releases/download/v${ver}/${tar}"
    download "$url" "$WORKDIR/$tar"
    tar -xzf "$WORKDIR/$tar" -C "$WORKDIR"
    local src="$WORKDIR/shadowsocks-libev-${ver}"
    [ -d "$src" ] || die "Source dir missing after extraction"

    # Build deps for fallback path only
    if [ "$pm" = "apt" ]; then
        DEBIAN_FRONTEND=noninteractive \
            apt-get -y -o Dpkg::Options::="--force-confdef" \
                       -o Dpkg::Options::="--force-confnew" \
                --no-install-recommends install \
            build-essential autoconf automake libtool pkg-config \
            libssl-dev libsodium-dev libmbedtls-dev libc-ares-dev \
            libev-dev zlib1g-dev gettext qrencode
    else
        $pm -y install gcc make autoconf automake libtool pkgconfig \
            openssl-devel libsodium-devel mbedtls-devel c-ares-devel \
            libev-devel zlib-devel gettext qrencode
    fi

    ( cd "$src" && \
      [ -x ./autogen.sh ] && ./autogen.sh || true
      ./configure --prefix=/usr --disable-documentation \
                  --with-mbedtls=/usr --with-sodium=/usr \
                  --with-cares=/usr --with-ev=/usr >/dev/null && \
      make -j"$(nproc)" >/dev/null && \
      make install >/dev/null ) || die "shadowsocks-libev build failed"
    ldconfig
    command -v ss-server >/dev/null || die "ss-server not found after build"
}

#==============================================================================
# 3. Install shadowsocks-rust (apt first, GitHub release binary fallback)
#==============================================================================
install_shadowsocks_rust() {
    if command -v ssserver >/dev/null; then
        log_info "shadowsocks-rust already installed"
        return 0
    fi

    local pm; pm=$(detect_pkg_manager)
    if [ "$pm" = "apt" ] && apt_has_package shadowsocks-rust; then
        log_info "Installing shadowsocks-rust via apt"
        DEBIAN_FRONTEND=noninteractive \
            apt-get -y -o Dpkg::Options::="--force-confdef" \
                       -o Dpkg::Options::="--force-confnew" \
                    install shadowsocks-rust \
            && command -v ssserver >/dev/null && return 0
    elif [ "$pm" = "dnf" ]; then
        dnf -y install shadowsocks-rust \
            && command -v ssserver >/dev/null && return 0
    fi

    # Fallback: GitHub release binary
    log_info "Downloading shadowsocks-rust from GitHub"
    local arch tar url
    arch=$(uname -m)
    case "$arch" in
        x86_64)        arch='x86_64-unknown-linux-gnu' ;;
        aarch64)       arch='aarch64-unknown-linux-gnu' ;;
        armv7l)        arch='armv7-unknown-linux-gnueabihf' ;;
        *)             die "Unsupported arch: $arch" ;;
    esac
    local ver
    ver=$(curl -fsSL https://api.github.com/repos/shadowsocks/shadowsocks-rust/releases/latest \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"v?([^"]+)".*/\1/') \
        || die "Cannot resolve latest shadowsocks-rust"
    tar="shadowsocks-${ver}.${arch}.tar.xz"
    url="https://github.com/shadowsocks/shadowsocks-rust/releases/download/v${ver}/${tar}"
    download "$url" "$WORKDIR/$tar"
    tar -xJf "$WORKDIR/$tar" -C "$WORKDIR"
    find "$WORKDIR" -maxdepth 2 -name 'ssserver' -type f -exec install -m 0755 {} /usr/local/bin/ \;
    find "$WORKDIR" -maxdepth 2 -name 'sslocal'   -type f -exec install -m 0755 {} /usr/local/bin/ \;
    command -v ssserver >/dev/null || die "ssserver not installed after fallback"
}

#==============================================================================
# 4. Install SIP003 plugin (apt first, GitHub release binary fallback)
#==============================================================================
install_plugin() {
    [ "$SS_PLUGIN" = "none" ] && return 0

    local pkg repo
    case "$SS_PLUGIN" in
        v2ray) pkg='v2ray-plugin'; repo='teddysun/v2ray-plugin' ;;
        xray)  pkg='xray-plugin';  repo='teddysun/xray-plugin'  ;;
        *)     die "Unknown plugin: $SS_PLUGIN" ;;
    esac

    if command -v apt-get >/dev/null && apt_has_package "$pkg"; then
        DEBIAN_FRONTEND=noninteractive \
            apt-get -y -o Dpkg::Options::="--force-confdef" \
                       -o Dpkg::Options::="--force-confnew" \
                    install "$pkg" \
            && command -v "$pkg" >/dev/null && return 0
    fi
    if command -v dnf >/dev/null; then
        dnf -y install "$pkg" 2>/dev/null \
            && command -v "$pkg" >/dev/null && return 0
    fi

    log_info "Downloading ${pkg} from GitHub"
    local arch asset url tar
    arch=$(uname -m); [ "$arch" = "x86_64" ] && arch='amd64' || arch='arm64-v8a'
    local ver
    ver=$(curl -fsSL "https://api.github.com/repos/${repo}/releases/latest" \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"v?([^"]+)".*/\1/') \
        || die "Cannot resolve latest ${pkg}"
    asset="${pkg}-linux-${arch}-v${ver}.tar.xz"
    url="https://github.com/${repo}/releases/download/v${ver}/${asset}"
    download "$url" "$WORKDIR/${asset}"
    tar -xJf "$WORKDIR/${asset}" -C "$WORKDIR"
    local bin; bin=$(find "$WORKDIR" -maxdepth 2 -type f -executable | head -1)
    [ -n "$bin" ] || die "No binary in ${pkg} archive"
    install -m 0755 "$bin" "/usr/local/bin/${pkg}"
}

#==============================================================================
# 5. Config generation (libev + rust both supported, with optional plugin)
#==============================================================================
CONFIG_DIR='/etc/shadowsocks-libev'

# If we can drop privileges, return the user directive. Otherwise return
# an empty string. The function does NOT also warn — the caller decides.
user_field() {
    if can_drop_privileges; then
        printf ',\n    "user":"nobody"'
    fi
}

generate_config_libev() {
    local cfg uf
    cfg="${CONFIG_DIR}/config.json"
    mkdir -p "$CONFIG_DIR"
    uf=$(user_field)
    if [ "$SS_PLUGIN" != "none" ]; then
        cat > "$cfg" <<EOF
{
    "server":"0.0.0.0",
    "server_port":${SS_PORT},
    "password":"${SS_PASSWORD}",
    "timeout":300,
    "method":"${SS_CIPHER}",
    "fast_open":false,
    "nameserver":"1.0.0.1",
    "mode":"tcp_and_udp"${uf},
    "plugin":"${SS_PLUGIN}-plugin",
    "plugin_opts":"${SS_PLUGIN_OPTS}"
}
EOF
    else
        cat > "$cfg" <<EOF
{
    "server":"0.0.0.0",
    "server_port":${SS_PORT},
    "password":"${SS_PASSWORD}",
    "timeout":300,
    "method":"${SS_CIPHER}",
    "fast_open":false,
    "nameserver":"1.0.0.1",
    "mode":"tcp_and_udp"${uf}
}
EOF
    fi
    if ! can_drop_privileges; then
        log_warn "Cannot drop to 'nobody' (container/limited env); ss-server will run as root"
    fi
    if ! can_drop_privileges; then
        log_warn "Cannot drop privileges (container/limited env); ss-server will run as root"
    fi
    chmod 640 "$cfg"
    CONFIG_FILE="$cfg"
}

generate_config_rust() {
    local cfg uf
    cfg="${CONFIG_DIR}/shadowsocks-rust-config.json"
    mkdir -p "$CONFIG_DIR"
    uf=$(user_field)
    if [ "$SS_PLUGIN" != "none" ]; then
        cat > "$cfg" <<EOF
{
    "server":"::",
    "server_port":${SS_PORT},
    "password":"${SS_PASSWORD}",
    "timeout":300,
    "method":"${SS_CIPHER}",
    "fast_open":false,
    "mode":"tcp_and_udp"${uf},
    "plugin":"${SS_PLUGIN}-plugin",
    "plugin_opts":"${SS_PLUGIN_OPTS}"
}
EOF
    else
        cat > "$cfg" <<EOF
{
    "server":"::",
    "server_port":${SS_PORT},
    "password":"${SS_PASSWORD}",
    "timeout":300,
    "method":"${SS_CIPHER}",
    "fast_open":false,
    "mode":"tcp_and_udp"${uf}
}
EOF
    fi
    if ! can_drop_privileges; then
        log_warn "Cannot drop to 'nobody' (container/limited env); ssserver will run as root"
    fi
    if ! can_drop_privileges; then
        log_warn "Cannot drop privileges (container/limited env); ss-server will run as root"
    fi
    chmod 640 "$cfg"
    CONFIG_FILE="$cfg"
}

#==============================================================================
# 6. Service management
#==============================================================================
service_unit_name() {
    case "$SS_TYPE" in
        libev) echo "$LIBEV_SERVICE" ;;
        rust)  echo "$RUST_SERVICE"  ;;
        *)     die "Unknown type: $SS_TYPE" ;;
    esac
}

start_service() {
    local svc; svc=$(service_unit_name)
    if has_systemd; then
        # Always write our own unit, because the one shipped by the
        # shadowsocks-libev package on Debian 11 uses DynamicUser=true
        # which then can't read /etc/shadowsocks-libev/config.json and
        # fails with "Invalid config path". A drop-in override is also
        # unreliable across versions, so we install a complete unit.
        install_our_systemd_unit
    elif command -v service >/dev/null; then
        service "${svc%.service}" start 2>/dev/null || true
    else
        log_warn "No init system; ss-server/ssserver started manually if any"
    fi
}

# Write a hardened systemd unit that points directly at our config file
# (no $CONFFILE indirection) and uses a real user instead of DynamicUser.
install_our_systemd_unit() {
    local svc bin args
    svc=$(service_unit_name)
    if [ "$SS_TYPE" = "rust" ]; then
        bin=/usr/bin/ssserver
    else
        bin=/usr/bin/ss-server
    fi
    args=(-c "${CONFIG_FILE}" -u)
    if [ -n "${SS_PLUGIN:-}" ] && [ "$SS_PLUGIN" != "none" ]; then
        args+=(--plugin "${SS_PLUGIN}-plugin")
        args+=(--plugin-opts "$SS_PLUGIN_OPTS")
    fi

    # Always run as root. We don't trust that setgroups() works in every
    # container/namespace, and the systemd `User=nobody` directive in
    # the package-supplied unit is the source of the "Invalid config
    # path" error on Debian 11. ss-server itself doesn't strictly need
    # to drop privileges, especially when wrapped by systemd which can
    # apply its own sandboxing.
    local exec_args="${args[*]}"
    cat > "${SYSTEMD_DIR}/${svc}" <<EOF
[Unit]
Description=Shadowsocks-${SS_TYPE} server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
LimitNOFILE=32768
ExecStart=${bin} ${exec_args}
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
    if ! can_drop_privileges; then
        log_warn "Cannot drop privileges; running ss-server as root (CAP_NET_BIND_SERVICE only)"
    fi

    # Remove distro drop-in overrides (set above may have left one behind)
    rm -rf /etc/systemd/system/"${svc}".d 2>/dev/null

    systemctl daemon-reload
    systemctl enable "$svc" >/dev/null
    systemctl restart "$svc"
}

stop_service() {
    local svc; svc=$(service_unit_name)
    if has_systemd; then
        systemctl stop "$svc" 2>/dev/null || true
    elif command -v service >/dev/null; then
        service "${svc%.service}" stop 2>/dev/null || true
    fi
}

#==============================================================================
# 7. Summary + QR code
#==============================================================================
get_public_ip() {
    local ip
    for src in 'https://api.ipify.org' 'https://ifconfig.me' 'https://ipv4.icanhazip.com'; do
        ip=$(curl --silent --max-time 5 "$src" 2>/dev/null) || continue
        ip=$(printf '%s' "$ip" | tr -d '\n\r ')
        [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && { echo "$ip"; return; }
    done
    echo "YOUR_SERVER_IP"
}

print_qr() {
    command -v qrencode >/dev/null || return 0
    local ip tmp qr_code tmp1 tmp2 png
    ip=$(get_public_ip)
    if [ "$SS_PLUGIN" != "none" ]; then
        tmp1=$(echo -n "${SS_CIPHER}:${SS_PASSWORD}" | base64 -w0 | sed 's/=//g')
        tmp2=$(echo -n "${SS_PLUGIN}-plugin;${SS_PLUGIN_OPTS}" | base64 -w0 | sed 's/=//g')
        qr_code="ss://${tmp1}@${ip}:${SS_PORT}/?plugin=${tmp2}"
    else
        tmp=$(echo -n "${SS_CIPHER}:${SS_PASSWORD}@${ip}:${SS_PORT}" | base64 -w0)
        qr_code="ss://${tmp}"
    fi
    echo
    echo "Your QR code (also saved as PNG):"
    echo "$qr_code"
    png="/tmp/shadowsocks_${SS_TYPE}_qr.png"
    echo -n "$qr_code" | qrencode -s8 -o "$png" 2>/dev/null
    log_info "QR png: $png"
}

print_summary() {
    local ip plugin_str service_str
    ip=$(get_public_ip)
    if [ "$SS_PLUGIN" = "none" ]; then
        plugin_str="none"
    else
        plugin_str="${SS_PLUGIN}-plugin (${SS_PLUGIN_OPTS})"
    fi
    if has_systemd; then
        service_str="systemd"
    else
        service_str="manual"
    fi
    cat <<EOF | sed 's/^/  /' >&2

=================================================
Shadowsocks-${SS_TYPE} installed successfully
-------------------------------------------------
  Server IP   : $ip
  Port        : $SS_PORT
  Cipher      : $SS_CIPHER
  Password    : $SS_PASSWORD
  Plugin      : $plugin_str
  Service     : $service_str
  Config file : $CONFIG_FILE
=================================================

EOF
}

#==============================================================================
# 8. Main flow
#==============================================================================
disable_selinux() {
    if [ -s /etc/selinux/config ] && grep -q 'SELINUX=enforcing' /etc/selinux/config; then
        sed -i 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config
        setenforce 0 2>/dev/null || true
    fi
}

config_firewall() {
    local zone
    if command -v firewall-cmd >/dev/null && systemctl is-active firewalld >/dev/null 2>&1; then
        zone=$(firewall-cmd --get-default-zone)
        firewall-cmd --permanent --zone="$zone" --add-port="${SS_PORT}"/tcp >/dev/null 2>&1
        firewall-cmd --permanent --zone="$zone" --add-port="${SS_PORT}"/udp >/dev/null 2>&1
        firewall-cmd --reload >/dev/null 2>&1
        log_info "Opened ${SS_PORT}/tcp+udp in firewalld"
    elif command -v ufw >/dev/null && ufw status >/dev/null 2>&1; then
        ufw allow "${SS_PORT}"/tcp >/dev/null 2>&1
        ufw allow "${SS_PORT}"/udp >/dev/null 2>&1
        log_info "Opened ${SS_PORT}/tcp+udp in ufw"
    fi
}

do_install() {
    log_info "$SCRIPT_NAME $SCRIPT_VERSION starting on $(os_pretty)"
    log_info "Init system: $(has_systemd && echo systemd || echo 'sysv/none')"

    # CLI pre-validation
    is_type "$SS_TYPE"     || die "Unsupported --type: $SS_TYPE (only: ${SUPPORTED_TYPES[*]})"
    is_port "$SS_PORT"     || [ -z "$SS_PORT" ] || die "Invalid --port: $SS_PORT"
    is_cipher "$SS_CIPHER" || die "Invalid --cipher: $SS_CIPHER"

    # rust is the only one that supports SIP003 plugin out of the box
    if [ "$SS_TYPE" = "libev" ] && [ "$SS_PLUGIN" != "none" ]; then
        log_warn "--plugin only meaningful for rust; ignoring"
        SS_PLUGIN='none'
    fi

    # Two ways to run:
    #   (a) default / interactive — ask the user about every value
    #   (b) --auto                — fill in random port + random password,
    #                               use the default cipher, no plugin.
    # --auto does NOT override CLI values; if the user passed --port 443
    # we keep 443, only the fields they didn't specify get defaults.
    if [ "$AUTO_YES" = "1" ]; then
        SS_PORT="${SS_PORT:-$(gen_port)}"
        SS_PASSWORD="${SS_PASSWORD:-$(gen_password)}"
        log_info "Auto mode: using defaults (port=${SS_PORT}, cipher=${SS_CIPHER}, plugin=${SS_PLUGIN})"
    else
        interactive_ask   # auto-degrades to AUTO_YES if no TTY
    fi

    [ "${#SS_PASSWORD}" -ge 6 ] || die "Password must be at least 6 characters"

    disable_selinux
    config_firewall

    case "$SS_TYPE" in
        libev)
            install_shadowsocks_libev
            generate_config_libev
            start_service
            ;;
        rust)
            install_shadowsocks_rust
            install_plugin
            generate_config_rust
            start_service
            ;;
    esac

    print_qr
    print_summary
}

do_uninstall() {
    log_info "Uninstalling shadowsocks-${SS_TYPE} ..."
    stop_service
    local pm; pm=$(detect_pkg_manager)
    case "$SS_TYPE" in
        libev)
            if [ "$pm" = "apt" ]; then
                # Only try to remove packages that are actually installed.
                local pkgs=""
                apt_has_package shadowsocks-libev && pkgs="shadowsocks-libev$pkgs"
                dpkg -l v2ray-plugin 2>/dev/null | grep -q '^ii' && pkgs="$pkgs v2ray-plugin"
                dpkg -l xray-plugin  2>/dev/null | grep -q '^ii' && pkgs="$pkgs xray-plugin"
                if [ -n "$pkgs" ]; then
                    DEBIAN_FRONTEND=noninteractive apt-get -y remove $pkgs
                fi
            else
                rm -f /usr/local/bin/ss-server /usr/local/bin/ss-local \
                      /usr/local/bin/ss-tunnel /usr/local/bin/ss-redir \
                      /usr/local/bin/ss-manager
            fi
            # Always remove the systemd unit, config and logs.
            if has_systemd; then
                rm -f "${SYSTEMD_DIR}/shadowsocks-libev.service"
                rm -rf "${SYSTEMD_DIR}/shadowsocks-libev.service.d" 2>/dev/null
                systemctl daemon-reload
            fi
            rm -f "${CONFIG_DIR}/config.json"
            rm -rf "$CONFIG_DIR"
            rm -f /var/log/shadowsocks-libev.log
            ;;
        rust)
            if [ "$pm" = "apt" ]; then
                local pkgs=""
                apt_has_package shadowsocks-rust && pkgs="shadowsocks-rust$pkgs"
                dpkg -l v2ray-plugin 2>/dev/null | grep -q '^ii' && pkgs="$pkgs v2ray-plugin"
                dpkg -l xray-plugin  2>/dev/null | grep -q '^ii' && pkgs="$pkgs xray-plugin"
                if [ -n "$pkgs" ]; then
                    DEBIAN_FRONTEND=noninteractive apt-get -y remove $pkgs
                fi
            else
                rm -f /usr/local/bin/ssserver /usr/local/bin/sslocal
            fi
            if has_systemd; then
                rm -f "${SYSTEMD_DIR}/shadowsocks-rust.service"
                rm -rf "${SYSTEMD_DIR}/shadowsocks-rust.service.d" 2>/dev/null
                systemctl daemon-reload
            fi
            rm -f "${CONFIG_DIR}/shadowsocks-rust-config.json"
            rm -rf "$CONFIG_DIR"
            rm -f /var/log/shadowsocks-rust.log
            ;;
    esac
    log_info "Done."
}

main() {
    parse_args "$@"
    case "$ACTION" in
        install)   do_install ;;
        uninstall) do_uninstall ;;
        *)         usage ;;
    esac
}

main "$@"
