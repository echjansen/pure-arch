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

# ./pure-arch-cloud-init-ssh.sh -b sid -i 192.168.122.61 -c pure-arch-config-efi-ext4-luks-systemd.sh

GITHUB_USER="echjansen"
BRANCH="master"
BRANCH_QUALIFIER=""
IP_ADDRESS=""
VM_TYPE="virtualbox"
VM_NAME="Arch Linux"
CONFIG_FILE_SH="pure-arch-config-efi-ext4-systemd.sh"

while getopts "b:c:i:n:t:u:" arg; do
  case $arg in
    b)
      BRANCH="$OPTARG"
      ;;
    c)
      CONFIG_FILE_SH="$OPTARG"
      ;;
    i)
      IP_ADDRESS="$OPTARG"
      ;;
    n)
      VM_NAME="$OPTARG"
      ;;
    t)
      VM_TYPE="$OPTARG"
      ;;
    u)
      GITHUB_USER=${OPTARG}
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

if [ "$IP_ADDRESS" == "" ] && [ "$VM_TYPE" != "" ] && [ "$VM_NAME" != "" ]; then
  IP_ADDRESS=$(VBoxManage guestproperty get "${VM_NAME}" "/VirtualBox/GuestInfo/Net/0/V4/IP" | cut -f2 -d " ")
fi

set -o xtrace
ssh-keygen -R "$IP_ADDRESS"
ssh-keyscan -H "$IP_ADDRESS" >> ~/.ssh/known_hosts

ssh -t -i cloud-init/pure-arch.key root@"$IP_ADDRESS" "bash -c \"curl -sL https://raw.githubusercontent.com/${GITHUB_USER}/pure-arch/${BRANCH}/download${BRANCH_QUALIFIER}.sh | bash -s -- -b ${BRANCH}\""

if [ -z "$CONFIG_FILE_SH" ]; then
  ssh -t -i cloud-init/pure-arch.key root@"$IP_ADDRESS"
else
  ssh -t -i cloud-init/pure-arch.key root@"$IP_ADDRESS" "bash -c \"configs/$CONFIG_FILE_SH\""
  ssh -t -i cloud-init/pure-arch.key root@"$IP_ADDRESS" "bash -c \"./pure-arch.sh -w\""
fi
