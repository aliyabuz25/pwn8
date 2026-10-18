#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x /opt/homebrew/bin/brew ]; then
    brew_cmd=/opt/homebrew/bin/brew
elif command -v brew >/dev/null 2>&1; then
    brew_cmd=$(command -v brew)
else
    printf '%s\n' 'Homebrew is required: https://brew.sh' >&2
    exit 1
fi
if [ "$(uname -s)" = Darwin ] && { [ ! -x tools/usb-reconnect ] || [ native/usb_reconnect.c -nt tools/usb-reconnect ]; }; then
    if ! command -v clang >/dev/null 2>&1; then
        printf '%s\n' 'A C compiler is required to rebuild the macOS USB reconnect helper.' >&2
        exit 1
    fi
    mkdir -p tools
    clang -O2 -Wall -Wextra -Werror native/usb_reconnect.c -framework IOKit -framework CoreFoundation -o tools/usb-reconnect
fi
"$brew_cmd" install gtk4 pygobject3 expat
if [ ! -x "$(dirname "$0")/../Legacy-iOS-Kit/bin/macos/ideviceinfo" ] && ! command -v ideviceinfo >/dev/null 2>&1; then
    "$brew_cmd" install libimobiledevice libirecovery
fi
