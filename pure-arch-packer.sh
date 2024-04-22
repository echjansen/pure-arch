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

CONFIG_FILE="pure-arch-packer.json"
BRANCH="master"
BRANCH_QUALIFIER=""
CONFIG_FILE_SH="pure-arch-config-efi-ext4-systemd.sh"

while getopts "b:c:" arg; do
  case $arg in
    b)
      BRANCH="$OPTARG"
      ;;
    c)
      CONFIG_FILE_SH="$OPTARG"
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

if [ "$BRANCH" == "sid" ]; then
  BRANCH_QUALIFIER="-sid"
fi

packer validate "packer/$CONFIG_FILE"
packer build -force -on-error=ask -var "branch=$BRANCH branch_qualifier=$BRANCH_QUALIFIER config_file_sh=$CONFIG_FILE_SH" "configs/$CONFIG_FILE"
