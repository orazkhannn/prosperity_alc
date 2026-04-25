#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/.." && pwd)"

os_name="$(uname -s)"

default_cargo_home="${repo_root}/.local-home/.cargo"
default_rustup_home="${repo_root}/.local-home/.rustup"
default_target_dir="${repo_root}/.cargo-target"

if [ -z "${CARGO_HOME-}" ] && [ -d "${default_cargo_home}" ]; then
    CARGO_HOME="${default_cargo_home}"
fi

if [ -z "${RUSTUP_HOME-}" ] && [ -d "${default_rustup_home}" ]; then
    RUSTUP_HOME="${default_rustup_home}"
fi

cargo_bin_root="${CARGO_HOME:-${HOME}/.cargo}"
cargo_bin="${cargo_bin_root}/bin/cargo"
clean_path="${cargo_bin_root}/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

effective_target_dir() {
    if [ -n "${CARGO_TARGET_DIR-}" ]; then
        printf '%s\n' "${CARGO_TARGET_DIR}"
        return
    fi

    if [ -d "${repo_root}" ]; then
        printf '%s\n' "${default_target_dir}"
        return
    fi

    case "${os_name}" in
        Darwin) printf '%s\n' "${HOME}/Library/Caches/rust_backtester/target" ;;
        *) printf '\n' ;;
    esac
}

case "${1-}" in
    --print-target-dir)
        effective_target_dir
        exit 0
        ;;
    --print-clean-path)
        printf '%s\n' "${clean_path}"
        exit 0
        ;;
esac

if [ ! -x "${cargo_bin}" ]; then
    echo "cargo not found at ${cargo_bin}" >&2
    exit 127
fi

if [ "${os_name}" != "Darwin" ]; then
    exec "${cargo_bin}" "$@"
fi

target_dir="$(effective_target_dir)"
if [ -n "${target_dir}" ]; then
    mkdir -p "${target_dir}"
fi

if [ -n "${PYO3_PYTHON-}" ]; then
    pyo3_python="${PYO3_PYTHON}"
else
    pyo3_python="$(command -v python3 2>/dev/null || printf '%s\n' python3)"
fi

exec env -i \
    HOME="${HOME}" \
    USER="${USER-}" \
    LOGNAME="${LOGNAME-${USER-}}" \
    PATH="${clean_path}" \
    TMPDIR="${TMPDIR-/tmp}" \
    TERM="${TERM-dumb}" \
    CARGO_TARGET_DIR="${target_dir}" \
    ${CARGO_HOME+"CARGO_HOME=${CARGO_HOME}"} \
    ${RUSTUP_HOME+"RUSTUP_HOME=${RUSTUP_HOME}"} \
    ${HTTP_PROXY+"HTTP_PROXY=${HTTP_PROXY}"} \
    ${HTTPS_PROXY+"HTTPS_PROXY=${HTTPS_PROXY}"} \
    ${NO_PROXY+"NO_PROXY=${NO_PROXY}"} \
    ${SSL_CERT_FILE+"SSL_CERT_FILE=${SSL_CERT_FILE}"} \
    ${SSL_CERT_DIR+"SSL_CERT_DIR=${SSL_CERT_DIR}"} \
    PYO3_PYTHON="${pyo3_python}" \
    "${cargo_bin}" "$@"