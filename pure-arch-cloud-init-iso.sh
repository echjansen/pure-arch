#!/usr/bin/env bash
set -eu
set -o xtrace

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


if [ ! -f cloud-init/pure-arch.key ]; then
    openssl genrsa -out cloud-init/pure-arch.key 8192
fi
SSH_RSA=$(ssh-keygen -y -f cloud-init/pure-arch.key)
mkdir -p cloud-init/iso/
cp cloud-init/meta-data cloud-init/user-data cloud-init/iso/
sed -i "s#\\\${SSH_RSA}#${SSH_RSA}#" cloud-init/iso/user-data
mkisofs -o cloud-init/pure-arch-cloud-init.iso -V CIDATA -iso-level 3 -J -R cloud-init/iso/
