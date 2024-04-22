#!/usr/bin/env bash
set -eu

sed -i "s/LOG=.*/LOG=\"false\"/" ./pure-arch.conf
sed -i "s#DEVICE=.*#DEVICE=\"auto\"#" ./pure-arch.conf
sed -i "s/FILE_SYSTEM_TYPE=.*/FILE_SYSTEM_TYPE=\"ext4\"/" ./pure-arch.conf
sed -i "s/LVM=.*/LVM=\"false\"/" ./pure-arch.conf
sed -i "s/LUKS_PASSWORD=.*/LUKS_PASSWORD=\"\"/" ./pure-arch.conf
sed -i "s/LUKS_PASSWORD_RETYPE=.*/LUKS_PASSWORD_RETYPE=\"\"/" ./pure-arch.conf
sed -i "s/ROOT_PASSWORD=.*/ROOT_PASSWORD=\"archlinux\"/" ./pure-arch.conf
sed -i "s/ROOT_PASSWORD_RETYPE=.*/ROOT_PASSWORD_RETYPE=\"archlinux\"/" ./pure-arch.conf
sed -i "s/USER_PASSWORD=.*/USER_PASSWORD=\"archlinux\"/" ./pure-arch.conf
sed -i "s/USER_PASSWORD_RETYPE=.*/USER_PASSWORD_RETYPE=\"archlinux\"/" ./pure-arch.conf
sed -i "s/BOOTLOADER=.*/BOOTLOADER=\"systemd\"/" ./pure-arch.conf
sed -i "s/DESKTOP_ENVIRONMENT=.*/DESKTOP_ENVIRONMENT=\"gnome\"/" ./pure-arch.conf
sed -i "s/PACKAGES_INSTALL=.*/PACKAGES_INSTALL=\"true\"/" ./pure-arch.conf
sed -i "s/PACKAGES_PIPEWIRE=.*/PACKAGES_PIPEWIRE=\"true\"/" ./pure-arch.conf
sed -i "s/PACKAGES_FLATPAK_INSTALL=.*/PACKAGES_FLATPAK_INSTALL=\"true\"/" ./pure-arch-packages.conf
sed -i "s/PACKAGES_FLATPAK_CUSTOM=.*/PACKAGES_FLATPAK_CUSTOM=\"org.videolan.VLC\"/" ./pure-arch-packages.conf
sed -i "s/PACKAGES_SDKMAN_INSTALL=.*/PACKAGES_SDKMAN_INSTALL=\"true\"/" ./pure-arch-packages.conf
sed -i "s/PACKAGES_SDKMAN_SDKS=.*/PACKAGES_SDKMAN_SDKS=\"java:17.0.1-tem\"/" ./pure-arch-packages.conf
