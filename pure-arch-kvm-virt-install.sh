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

# https://wiki.archlinux.org/title/Libvirt#Server
# https://wiki.archlinux.org/title/QEMU#Bridged_networking_using_qemu-bridge-helper
# sudo pacman -S virt-install dnsmasq dmidecode
# sudo usermod -a -G libvirtd echjansen
# sudo systemctl start libvirtd.service
# mkdir -p /etc/qemu
# vim /etc/qemu/bridge.conf
# allow virbr0

# 3D Acceleration
# Host and guest shared clipboard
# Host and guest file sharing

DISK_DIRECTORY="/run/media/echjansen/Samsung microSD/KVM VMs"
ISO_DIRECTORY="/run/media/echjansen/Samsung microSD/Iso"

virt-install \
    --connect=qemu:///session \
    --name archlinux-pure-arch \
    --os-variant archlinux \
    --vcpu 2 \
    --ram 4096 \
    --boot uefi \
    --disk path="$DISK_DIRECTORY/archlinux-pure-arch.qcow2,format=qcow2,size=40,sparse=yes" \
    --cdrom "$ISO_DIRECTORY/archlinux-x86_64.iso" \
    --disk cloud-init/pure-arch-cloud-init.iso,device=cdrom,bus=sata \
    --network bridge=virbr0 \
    --noautoconsole
