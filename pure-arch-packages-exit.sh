#!/usr/bin/env bash
set -eu

# Copyright (C) 2024 echjansen

# This file is part of = P U R E - A R C H =

# pure-arch is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or (at
# your option) any later version.

# pure-arch is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with pure-emacs.  If not, see <http://www.gnu.org/licenses/>.

# Pure Arch installs an Arch Linux operating system
# unattended, automated, customized and secured.

LOG_FILE="pure-arch-packages.log"
ASCIINEMA_FILE="pure-arch-packages.asciinema"

function copy_logs() {
    if [ -f "$LOG_FILE" ]; then
        sudo mkdir -p /var/log/pure-arch
        sudo cp "$LOG_FILE" "/var/log/pure-arch/$LOG_FILE"
    fi
    if [ -f "$ASCIINEMA_FILE" ]; then
        sudo mkdir -p /var/log/pure-arch
        sudo cp "$ASCIINEMA_FILE" "/var/log/pure-arch/$ASCIINEMA_FILE"
    fi
}

copy_logs
