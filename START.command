#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Homebrew Python needs a newer libexpat than the macOS 26.0 system copy.
for expat_dir in /opt/homebrew/opt/expat/lib /usr/local/opt/expat/lib; do
    if [ -f "$expat_dir/libexpat.1.dylib" ]; then
        export DYLD_LIBRARY_PATH="$expat_dir${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
        break
    fi
done
for candidate in /opt/homebrew/Cellar/python@3.14/3.14.0_1/bin/python3.14 /opt/homebrew/opt/python@3.14/libexec/bin/python3 /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if "$candidate" -c 'import plistlib; import gi; gi.require_version("Gtk", "4.0")' >/dev/null 2>&1; then
        exec "$candidate" -m remed1st "$@"
    fi
done
printf '%s\n' 'GTK4/PyGObject is missing. Run SETUP.command.' >&2
exit 1
