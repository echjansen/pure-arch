#!/usr/bin/env -S bash -e

# Cleaning the TTY.
clear
setfont ter-v22b

# Cosmetics (colours for text).
BOLD='\e[1m'
BRED='\e[91m'
BBLUE='\e[34m'  
BGREEN='\e[92m'
BYELLOW='\e[93m'
RESET='\e[0m'

# Pretty print (function).
intro_print () {
    echo -e "${BOLD}${BGREEN}$1${RESET}"
}

info_print () {
    echo -e "${BOLD}${BGREEN}[ ${BYELLOW}•${BGREEN} ] $1${RESET}"
}

# Pretty print for input (function).
input_print () {
    echo -ne "${BOLD}${BYELLOW}[ ${BGREEN}•${BYELLOW} ] $1${RESET}"
}

# Alert user of bad input (function).
error_print () {
    echo -e "${BOLD}${BRED}[ ${BBLUE}•${BRED} ] $1${RESET}"
}

# Selecting the kernel flavor to install.
kernel_selector () {
    info_print "List of kernels:"
    info_print "================"
    info_print "1) Stable:     Vanilla Linux kernel with a few specific Arch Linux patches applied"
    info_print "2) Hardened:   A security-focused Linux kernel"
    info_print "3) Longterm:   Long-term support (LTS) Linux kernel"
    info_print "4) Zen Kernel: A Linux kernel optimized for desktop usage"
    input_print "Please select the number of the corresponding kernel (e.g. 1): " 
    read -r choice    
    case $choice in
        1 ) kernel=linux
            ;;
        2 ) kernel=linux-hardened
            ;;
        3 ) kernel=linux-lts
            ;;
        4 ) kernel=linux-zen
            ;;
        * ) error_print "You did not enter a valid kernel, please try again."
            return 1
    esac
}

# Virtualization check (function).
virt_check () {
    hypervisor=$(systemd-detect-virt)
    case $hypervisor in
        kvm )   info_print "KVM has been detected, setting up guest tools."
                pacstrap /mnt qemu-guest-agent &>/dev/null
                systemctl enable qemu-guest-agent --root=/mnt &>/dev/null
                ;;
        vmware  )   info_print "VMWare Workstation/ESXi has been detected, setting up guest tools."
                    pacstrap /mnt open-vm-tools >/dev/null
                    systemctl enable vmtoolsd --root=/mnt &>/dev/null
                    systemctl enable vmware-vmblock-fuse --root=/mnt &>/dev/null
                    ;;
        oracle )    info_print "VirtualBox has been detected, setting up guest tools."
                    pacstrap /mnt virtualbox-guest-utils &>/dev/null
                    systemctl enable vboxservice --root=/mnt &>/dev/null
                    ;;
        microsoft ) info_print "Hyper-V has been detected, setting up guest tools."
                    pacstrap /mnt hyperv &>/dev/null
                    systemctl enable hv_fcopy_daemon --root=/mnt &>/dev/null
                    systemctl enable hv_kvp_daemon --root=/mnt &>/dev/null
                    systemctl enable hv_vss_daemon --root=/mnt &>/dev/null
                    ;;
        * )         info_print "No virtualisation detected."
                    ;;
    esac
}

# User enters a password for the LUKS Container (function).
lukspass_selector () {
    input_print "Please enter a password for the LUKS container (password not visible): "
    read -r -s password
    if [[ -z "$password" ]]; then
        echo
        error_print "You need to enter a password for the LUKS Container, please try again."
        return 1
    fi
    echo
    input_print "Please enter the password for the LUKS container again (password not visible): "
    read -r -s password2
    echo
    if [[ "$password" != "$password2" ]]; then
        error_print "Passwords don't match, please try again."
        return 1
    fi
    return 0
}

# Setting up a password for the user account (function).
userpass_selector () {
    input_print "Please enter name for a user account (enter empty to not create one): "
    read -r username
    if [[ -z "$username" ]]; then
        return 0
    fi
    input_print "Please enter a password for $username (password not visible): "
    read -r -s userpass
    if [[ -z "$userpass" ]]; then
        echo
        error_print "You need to enter a password for $username, please try again."
        return 1
    fi
    echo
    input_print "Please enter the password again (password not visible): " 
    read -r -s userpass2
    echo
    if [[ "$userpass" != "$userpass2" ]]; then
        echo
        error_print "Passwords don't match, please try again."
        return 1
    fi
    return 0
}

# Setting up a password for the root account (function).
rootpass_selector () {
    input_print "Please enter a password for the root user (password not visible): "
    read -r -s rootpass
    if [[ -z "$rootpass" ]]; then
        echo
        error_print "You need to enter a password for the root user, please try again."
        return 1
    fi
    echo
    input_print "Please enter the password again (password not visible): " 
    read -r -s rootpass2
    echo
    if [[ "$rootpass" != "$rootpass2" ]]; then
        error_print "Passwords don't match, please try again."
        return 1
    fi
    return 0
}

# Microcode detector (function).
microcode_detector () {
    CPU=$(grep vendor_id /proc/cpuinfo)
    if [[ "$CPU" == *"AuthenticAMD"* ]]; then
        info_print "An AMD CPU has been detected, the AMD microcode will be installed."
        microcode="amd-ucode"
    else
        info_print "An Intel CPU has been detected, the Intel microcode will be installed."
        microcode="intel-ucode"
    fi
}

# User enters a hostname (function).
hostname_selector () {
    input_print "Please enter the hostname: "
    read -r hostname
    if [[ -z "$hostname" ]]; then
        error_print "You need to enter a hostname in order to continue."
        return 1
    fi
    return 0
}

# User chooses the locale (function).
locale_selector () {
    input_print "Please insert the locale you use (format: xx_XX. Enter empty to use -en_US-, or \"/\" to search locales): " locale
    read -r locale
    case "$locale" in
        '') locale="en_US.UTF-8"
            info_print "$locale will be the default locale."
            return 0;;
        '/') sed -E '/^# +|^#$/d;s/^#| *$//g;s/ .*/ (Charset:&)/' /etc/locale.gen | less -M
                clear
                return 1;;
        *)  if ! grep -q "^#\?$(sed 's/[].*[]/\\&/g' <<< "$locale") " /etc/locale.gen; then
                error_print "The specified locale doesn't exist or isn't supported."
                return 1
            fi
            return 0
    esac
}

# User chooses the console keyboard layout (function).
keyboard_selector () {
    input_print "Please insert the keyboard layout (empty to use -US-, or \"/\" to look up for keyboard layouts): "
    read -r kblayout
    case "$kblayout" in
        '') kblayout="us"
            info_print "The standard US keyboard layout will be used."
            return 0;;
        '/') localectl list-keymaps
             clear
             return 1;;
        *) if ! localectl list-keymaps | grep -Fxq "$kblayout"; then
               error_print "The specified keymap doesn't exist."
               return 1
           fi
        info_print "Changing console layout to $kblayout."
        loadkeys "$kblayout"
        return 0
    esac
}

intro_print "======================================"
intro_print "Welcome to P U R E - A R C H installer"
intro_print "======================================"
intro_print " "

## user input ##

# Choosing the target for the installation.
info_print "Available disks for the installation:"
PS3="Please select the number of the corresponding disk (e.g. 1): "
select ENTRY in $(lsblk -dpnoNAME|grep -P "/dev/sd|nvme|vd");
do
    DISK="$ENTRY"
    info_print "Pure Arch will be installed on the following disk: $DISK"
    break
done

# Select kernel
until kernel_selector; do : ; done

# Entering username and password.
until userpass_selector; do : ; done

# Entering root password.
until rootpass_selector; do : ; done

# Setting up LUKS password.
until lukspass_selector; do : ; done

# User choses the hostname.
until hostname_selector; do : ; done

# Setting up keyboard layout.
until keyboard_selector; do : ; done

# Setting up locale language.
until locale_selector; do : ; done

# Confirming the disk selection.
info_print "Ready to start installation."
input_print "This will delete the current partition table on $DISK. Do you agree [y/N]?" 
read -r response    
response=${response,,}
if [[ ! ("$response" =~ ^(yes|y)$) ]]; then
    error_print "No selected. Quitting the installation."
    exit
fi

## installation ##
clear
intro_print "======================================"
intro_print " Installing P U R E - A R C H ....... "
intro_print "======================================"
intro_print " "

# Speed-up the pacman download
info_print "Speed up pacman download"
sed -Ei 's/^#(Color)$/\1\nILoveCandy/;s/^#(ParallelDownloads).*/\1 = 10/' /etc/pacman.conf

# Updating the live environment usually causes more problems than its worth, and quite often can't be done without remounting cowspace with more capacity, especially at the end of any given month.
info_print "Updating pacman"
pacman -Sy &>/dev/null

# Installing curl
info_print "Installing curl"
pacman -S --noconfirm curl &>/dev/null

# formatting the disk
info_print "Formatting disk"
wipefs -af "$DISK" &>/dev/null
sgdisk -Zo "$DISK" &>/dev/null

# Checking the microcode to install.
info_print "Checking microcode"
CPU=$(grep vendor_id /proc/cpuinfo)
if [[ $CPU == *"AuthenticAMD"* ]]; then
    microcode=amd-ucode
else
    microcode=intel-ucode
fi

# Creating a new partition scheme.
info_print "Creating new partition scheme on $DISK."
parted -s "$DISK" \
    mklabel gpt \
    mkpart ESP fat32 1MiB 128MiB \
    set 1 esp on \
    mkpart cryptroot 128MiB 100% \

sleep 0.1
ESP="/dev/$(lsblk $DISK -o NAME,PARTLABEL | grep ESP| cut -d " " -f1 | cut -c7-)"
cryptroot="/dev/$(lsblk $DISK -o NAME,PARTLABEL | grep cryptroot | cut -d " " -f1 | cut -c7-)"

# Informing the Kernel of the changes.
info_print "Informing the Kernel about the disk changes."
partprobe "$DISK"

# Formatting the ESP as FAT32.
info_print "Formatting the EFI Partition as FAT32."
mkfs.fat -F 32 -s 2 $ESP &>/dev/null

# Creating a LUKS Container for the root partition.
info_print "Creating LUKS Container for the root partition."
echo -n "$password" | cryptsetup luksFormat --type luks1 $cryptroot -d - &>/dev/null

info_print "Opening the newly created LUKS Container."
echo -n "$password" | cryptsetup open $cryptroot cryptroot -d -
BTRFS="/dev/mapper/cryptroot"

# Formatting the LUKS Container as BTRFS.
info_print "Formatting the LUKS container as BTRFS."
mkfs.btrfs $BTRFS &>/dev/null
mount -o clear_cache,nospace_cache $BTRFS /mnt

# Creating BTRFS subvolumes.
info_print "Creating BTRFS subvolumes."
btrfs su cr /mnt/@ &>/dev/null
btrfs su cr /mnt/@/.snapshots &>/dev/null
mkdir -p /mnt/@/.snapshots/1 &>/dev/null
btrfs su cr /mnt/@/.snapshots/1/snapshot &>/dev/null
btrfs su cr /mnt/@/boot/ &>/dev/null
btrfs su cr /mnt/@/home &>/dev/null
btrfs su cr /mnt/@/root &>/dev/null
btrfs su cr /mnt/@/srv &>/dev/null
btrfs su cr /mnt/@/var_log &>/dev/null
btrfs su cr /mnt/@/var_log_journal &>/dev/null
btrfs su cr /mnt/@/var_crash &>/dev/null
btrfs su cr /mnt/@/var_cache &>/dev/null
btrfs su cr /mnt/@/var_tmp &>/dev/null
btrfs su cr /mnt/@/var_spool &>/dev/null
btrfs su cr /mnt/@/var_lib_libvirt_images &>/dev/null
btrfs su cr /mnt/@/var_lib_machines &>/dev/null
btrfs su cr /mnt/@/var_lib_gdm &>/dev/null
btrfs su cr /mnt/@/var_lib_AccountsService &>/dev/null
btrfs su cr /mnt/@/cryptkey &>/dev/null

chattr +C /mnt/@/boot
chattr +C /mnt/@/srv
chattr +C /mnt/@/var_log
chattr +C /mnt/@/var_log_journal
chattr +C /mnt/@/var_crash
chattr +C /mnt/@/var_cache
chattr +C /mnt/@/var_tmp
chattr +C /mnt/@/var_spool
chattr +C /mnt/@/var_lib_libvirt_images
chattr +C /mnt/@/var_lib_machines
chattr +C /mnt/@/var_lib_gdm
chattr +C /mnt/@/var_lib_AccountsService
chattr +C /mnt/@/cryptkey

#Set the default BTRFS Subvol to Snapshot 1 before pacstrapping
info_print "Set the default BTRFS subvol to Snapshot 1"
btrfs subvolume set-default "$(btrfs subvolume list /mnt | grep "@/.snapshots/1/snapshot" | grep -oP '(?<=ID )[0-9]+')" /mnt

cat << EOF >> /mnt/@/.snapshots/1/info.xml
<?xml version="1.0"?>
<snapshot>
  <type>single</type>
  <num>1</num>
  <date>1999-03-31 0:00:00</date>
  <description>First Root Filesystem</description>
  <cleanup>number</cleanup>
</snapshot>
EOF

chmod 600 /mnt/@/.snapshots/1/info.xml

# Mounting the newly created subvolumes.
info_print "Mounting the newly created subvolumes."
umount /mnt
mount -o ssd,noatime,space_cache,compress=zstd:15 $BTRFS /mnt
mkdir -p /mnt/{boot,root,home,.snapshots,srv,tmp,/var/log,/var/crash,/var/cache,/var/tmp,/var/spool,/var/lib/libvirt/images,/var/lib/machines,/var/lib/gdm,/var/lib/AccountsService,/cryptkey}
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodev,nosuid,noexec,subvol=@/boot $BTRFS /mnt/boot
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodev,nosuid,subvol=@/root $BTRFS /mnt/root
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodev,nosuid,subvol=@/home $BTRFS /mnt/home
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,subvol=@/.snapshots $BTRFS /mnt/.snapshots
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,subvol=@/srv $BTRFS /mnt/srv
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_log $BTRFS /mnt/var/log

# Toolbox (https://github.com/containers/toolbox) needs /var/log/journal to have dev, suid, and exec, Thus I am splitting the subvolume. Need to make the directory after /mnt/var/log/ has been mounted.
mkdir -p /mnt/var/log/journal
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,subvol=@/var_log_journal $BTRFS /mnt/var/log/journal

mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_crash $BTRFS /mnt/var/crash
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_cache $BTRFS /mnt/var/cache
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_tmp $BTRFS /mnt/var/tmp

mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_spool $BTRFS /mnt/var/spool
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_lib_libvirt_images $BTRFS /mnt/var/lib/libvirt/images
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/var_lib_machines $BTRFS /mnt/var/lib/machines

# The encryption is splitted as we do not want to include it in the backup with snap-pac.
mount -o ssd,noatime,space_cache=v2,autodefrag,compress=zstd:15,discard=async,nodatacow,nodev,nosuid,noexec,subvol=@/cryptkey $BTRFS /mnt/cryptkey

mkdir -p /mnt/boot/efi
mount -o nodev,nosuid,noexec $ESP /mnt/boot/efi

# Pacstrap (setting up a base sytem onto the new root).
# This will install some packages to "bootstrap" methaphorically our system.
# "base, linux, linux-firmware" are needed. If you want a more stable kernel, then swap linux with linux-lts
# "base-devel" base development packages
# "efibootmgr" support EFI boot
# "git" to install the git vcs
# "btrfs-progs" are user-space utilities for file system management ( needed to harness the potential of btrfs )
# "grub" the bootloader
# "grub-btrfs" support for btrfgs in grub
# "snapper" creating btrfs snapshots
# "snap-pac" create snapshots automatically in pacman actions
# "inotify-tools" support snapper
# "grub-btrfs" adds btrfs support for the grub bootloader and enables the user to directly boot from snapshots
# "inotify-tools" used by grub btrfsd deamon to automatically spot new snapshots and update grub entries
# "timeshift" a GUI app to easily create,plan and restore snapshots using BTRFS capabilities
# "intel(amd)-ucode" microcode updates for the cpu. If you have an intel one use "intel-ucode"
# "firewalld" firewall services
# "apparmor" restrict applications access
# "fwupd" make updating firmware on Linux automatic
# "mg" micro emacs editor
# "chrony" secure NTP alternative
# "networkmanager" to manage Internet connections both wired and wireless ( it also has an applet package network-manager-applet )
# "pipewire pipewire-alsa pipewire-pulse pipewire-jack" for the new audio framework replacing pulse and jack. 
# "wireplumber" the pipewire session manager.
# "reflector" to manage mirrors for pacman
# "openssh" to use ssh and manage keys
# "man" for manual pages
# "sudo" to run commands as other users
# "zram-generator" configure zram swap devices
# "git" version management
# "gnupg" gnu pretty good privacy
# "xdg-user-dirs" home folder subdirectories
# "chezmoi" dotfile management
# "rbw" bitwarden password client
info_print "Installing the base system, please wait ..."
pacstrap /mnt base ${kernel} ${microcode} linux-firmware base-devel btrfs-progs grub grub-btrfs snapper snap-pac inotify-tools efibootmgr sudo networkmanager apparmor firewalld zram-generator reflector openssh chrony fwupd pipewire pipewire-alsa pipewire-pulse pipewire-jack wireplumber man git gnupg rbw xdg-user-dirs chezmoi mg &>/dev/null

# Generating /etc/fstab.
info_print "Generating a new fstab."
genfstab -U /mnt >> /mnt/etc/fstab
sed -i 's#,subvolid=258,subvol=/@/.snapshots/1/snapshot,subvol=@/.snapshots/1/snapshot##g' /mnt/etc/fstab

info_print "Setting hostname to $hostame" 
echo "$hostname" > /mnt/etc/hostname

# Setting hosts file.
info_print "Setting hosts file."
cat > /mnt/etc/hosts <<EOF
127.0.0.1   localhost
::1         localhost
127.0.1.1   $hostname.localdomain   $hostname
EOF

# Setting up locales.
info_print "Setting locales."
sed -i "/^#$locale/s/^#//" /mnt/etc/locale.gen
echo "LANG=$locale" > /mnt/etc/locale.conf

# Setting up keyboard layout.
info_print "Setting keyboard layout." 
echo "KEYMAP=$kblayout" > /mnt/etc/vconsole.conf

# Setting up pacman
info_print "Setting pacman configuration."
sed -Ei 's/^#(Color)$/\1\nILoveCandy/;s/^#(ParallelDownloads).*/\1 = 10/' /mnt/etc/pacman.conf

# Configuring /etc/mkinitcpio.conf
info_print "Configuring /etc/mkinitcpio for ZSTD compression and LUKS hook."
sed -i 's,#COMPRESSION="zstd",COMPRESSION="zstd",g' /mnt/etc/mkinitcpio.conf
sed -i 's,HOOKS=(base udev autodetect microcode modconf kms keyboard keymap consolefont block filesystems fsck),HOOKS=(base udev autodetect microcode modconf kms keyboard keymap consolefont block encrypt filesystems fsck),g' /mnt/etc/mkinitcpio.conf

# Enabling LUKS in GRUB and setting the UUID of the LUKS container.
UUID=$(blkid $cryptroot | cut -f2 -d'"')
sed -i 's/#\(GRUB_ENABLE_CRYPTODISK=y\)/\1/' /mnt/etc/default/grub
echo "" >> /mnt/etc/default/grub
echo -e "# Booting with BTRFS subvolume\nGRUB_BTRFS_OVERRIDE_BOOT_PARTITION_DETECTION=true" >> /mnt/etc/default/grub
sed -i 's#rootflags=subvol=${rootsubvol}##g' /mnt/etc/grub.d/10_linux
sed -i 's#rootflags=subvol=${rootsubvol}##g' /mnt/etc/grub.d/20_linux_xen

info_print "Securing Linux"
# Enabling CPU Mitigations
info_print "... Enabling CPU mitigation."
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/etc/default/grub.d/40_cpu_mitigations.cfg -o /mnt/etc/grub.d/40_cpu_mitigations.cfg &>/dev/null

# Distrusting the CPU
info_print "... Distrusting the CPU."
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/etc/default/grub.d/40_distrust_cpu.cfg -o /mnt/etc/grub.d/40_distrust_cpu.cfg &>/dev/null

# Enabling IOMMU
info_print "... Enabling IOMMU."
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/etc/default/grub.d/40_enable_iommu.cfg -o /mnt/etc/grub.d/40_enable_iommu.cfg &>/dev/null

# Enabling NTS
info_print "... Enabling NTS."
curl https://raw.githubusercontent.com/GrapheneOS/infrastructure/main/chrony.conf -o /mnt/etc/chrony.conf &>/dev/null

# Setting GRUB configuration file permissions
info_print "... Setting GRUB configuration permissions."
chmod 755 /mnt/etc/grub.d/*

# Adding keyfile to the initramfs to avoid double password.
info_print "... Adding keyfile to initramfs"
dd bs=512 count=4 if=/dev/random of=/mnt/cryptkey/.root.key iflag=fullblock &>/dev/null
chmod 000 /mnt/cryptkey/.root.key &>/dev/null
echo -n "$password" | cryptsetup -v luksAddKey /dev/disk/by-partlabel/cryptroot /mnt/cryptkey/.root.key -d - &>/dev/null

sed -i "s#quiet#cryptdevice=UUID=$UUID:cryptroot root=$BTRFS lsm=landlock,lockdown,yama,apparmor,bpf cryptkey=rootfs:/cryptkey/.root.key#g" /mnt/etc/default/grub
sed -i 's#FILES=()#FILES=(/cryptkey/.root.key)#g' /mnt/etc/mkinitcpio.conf

# Configure AppArmor Parser caching
info_print "... Configuring AppArmor parser caching."
sed -i 's/#write-cache/write-cache/g' /mnt/etc/apparmor/parser.conf
sed -i 's,#Include /etc/apparmor.d/,Include /etc/apparmor.d/,g' /mnt/etc/apparmor/parser.conf

# Blacklisting kernel modules
info_print "... Blacklisting kernel modules."
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/etc/modprobe.d/30_security-misc.conf -o /mnt/etc/modprobe.d/30_security-misc.conf &>/dev/null
chmod 600 /mnt/etc/modprobe.d/*

# Security kernel settings.
info_print "... Securing kernel settings"
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/usr/lib/sysctl.d/990-security-misc.conf -o /mnt/etc/sysctl.d/990-security-misc.conf &>/dev/null
sed -i 's/kernel.yama.ptrace_scope=2/kernel.yama.ptrace_scope=3/g' /mnt/etc/sysctl.d/990-security-misc.conf
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/etc/sysctl.d/30_silent-kernel-printk.conf -o /mnt/etc/sysctl.d/30_silent-kernel-printk.conf &>/dev/null
curl https://raw.githubusercontent.com/Kicksecure/security-misc/master/etc/sysctl.d/30_security-misc_kexec-disable.conf -o /mnt/etc/sysctl.d/30_security-misc_kexec-disable.conf &>/dev/null
chmod 600 /mnt/etc/sysctl.d/*

# Remove nullok from system-auth
info_print "... Removing nullok from system-auth."
sed -i 's/nullok//g' /mnt/etc/pam.d/system-auth

# Disable coredump
info_print "... Disabling coredump."
echo "* hard core 0" >> /mnt/etc/security/limits.conf

# Disable su for non-wheel users
info_print "... Disabling su for non-wheel users."
bash -c 'cat > /mnt/etc/pam.d/su' <<-'EOF'
#%PAM-1.0
auth		sufficient	pam_rootok.so
# Uncomment the following line to implicitly trust users in the "wheel" group.
#auth		sufficient	pam_wheel.so trust use_uid
# Uncomment the following line to require a user to be in the "wheel" group.
auth		required	pam_wheel.so use_uid
auth		required	pam_unix.so
account		required	pam_unix.so
session		required	pam_unix.so
EOF

# Configuring the system.
info_print "Configuring the system - chroot"

# ZRAM configuration
info_print "... Configuring zram."
bash -c 'cat > /mnt/etc/systemd/zram-generator.conf' <<-'EOF'
[zram0]
zram-fraction = 1
max-zram-size = 8192
EOF

info_print "... Configuring timezone."
arch-chroot /mnt ln -sf /usr/share/zoneinfo/$(curl -s http://ip-api.com/line?fields=timezone) /etc/localtime &>/dev/null

info_print "... Configuring clock."
arch-chroot /mnt hwclock --systohc

info_print "... Configuring locales."
arch-chroot /mnt locale-gen &>/dev/null

info_print "... Adding $username with root privilege."
if [ -n "$username" ]; then
    arch-chroot /mnt useradd -m $username
    arch-chroot /mnt usermod -aG wheel $username

    arch-chroot /mnt groupadd -r audit
    arch-chroot /mnt gpasswd -a $username audit &>/dev/null
fi

# Setting user password.
if [[ -n "$username" ]]; then
    info_print "... Setting $username password."
    echo "$username:$userpass" | arch-chroot /mnt chpasswd
fi

# Setting root password.
info_print "... Setting root password."
echo "root:$rootpass" | arch-chroot /mnt chpasswd

# Giving wheel user sudo access.
info_print "... Setting user sudo access."
sed -i 's/# \(%wheel ALL=(ALL\(:ALL\|\)) ALL\)/\1/g' /mnt/etc/sudoers

# Change audit logging group
info_print "... Adding audit to logging group."
echo "log_group = audit" >> /mnt/etc/audit/auditd.conf

# Generating a new initramfs.
# info_print "... Create ram disk for kernel modules."
chmod 600 /mnt/boot/initramfs-linux*
arch-chroot /mnt mkinitcpio -P &>/dev/null
    
info_print "... Installing GRUB on /boot."
arch-chroot /mnt grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=GRUB --modules="normal test efi_gop efi_uga search echo linux all_video gfxmenu gfxterm_background gfxterm_menu gfxterm loadenv configfile gzio part_gpt cryptodisk luks gcry_rijndael gcry_sha256 btrfs" --disable-shim-lock &>/dev/null

info_print "... Configuring GRUB config file."
arch-chroot /mnt grub-mkconfig -o /boot/grub/grub.cfg &>/dev/null

# info_print "... Configuring snapshots."
arch-chroot /mnt /bin/bash -e <<EOF

    # Generating a new initramfs.
    # echo -e "${BOLD}${BGREEN}[ ${BYELLOW}•${BGREEN} ] ... Create ram disk for kernel modules.${RESET}"
    # chmod 600 /boot/initramfs-linux* # &>/dev/null
    # mkinitcpio -P # &>/dev/null

    # Installing GRUB.
    # echo -e "${BOLD}${BGREEN}[ ${BYELLOW}•${BGREEN} ]  ... Installing GRUB on /boot.${RESET}"
    # grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=GRUB --modules="normal test efi_gop efi_uga search echo linux all_video gfxmenu gfxterm_background gfxterm_menu gfxterm loadenv configfile gzio part_gpt cryptodisk luks gcry_rijndael gcry_sha256 btrfs" --disable-shim-lock # &>/dev/null

    # Creating grub config file.
    # echo -e "${BOLD}${BGREEN}[ ${BYELLOW}•${BGREEN} ]  ... Configuring GRUB config file.${RESET}"
    # grub-mkconfig -o /boot/grub/grub.cfg # &>/dev/null

    # Snapper configuration
    echo -e "${BOLD}${BGREEN}[ ${BYELLOW}•${BGREEN} ]  ... Configuring snapshots.${RESET}"
    umount /.snapshots
    rm -r /.snapshots
    snapper --no-dbus -c root create-config /
    btrfs subvolume delete /.snapshots # &>/dev/null
    mkdir /.snapshots
    mount -a
    chmod 750 /.snapshots    
EOF

info_print "Enabling services"

# Enabling audit service.
info_print "... Enabling audit deamon service"
systemctl enable auditd --root=/mnt &>/dev/null

# Enabling openssh server
info_print "... Enabling openssh service"
systemctl enable sshd --root=/mnt &>/dev/null

# Enabling auto-trimming service.
info_print "... Enabling trimming service"
systemctl enable fstrim.timer --root=/mnt &>/dev/null

# Enabling NetworkManager.
info_print "... Enabling network manager service"
systemctl enable NetworkManager --root=/mnt &>/dev/null

# Enabling AppArmor.
info_print "... Enabling apparmor service"
systemctl enable apparmor --root=/mnt &>/dev/null

# Enabling Firewalld.
info_print "... Enabling firewalld service"
systemctl enable firewalld --root=/mnt &>/dev/null

# Enabling Reflector timer.
info_print "... Enabling reflector service"
systemctl enable reflector.timer --root=/mnt &>/dev/null

# Enabling systemd-oomd.
info_print "... Enabling oom daemon"
systemctl enable systemd-oomd --root=/mnt &>/dev/null

# Disabling systemd-timesyncd
info_print "... Disabling timesync daemon"
systemctl disable systemd-timesyncd --root=/mnt &>/dev/null

# Enabling chronyd
info_print "... Enabling chrony daemon"
systemctl enable chronyd --root=/mnt &>/dev/null

# Enabling Snapper automatic snapshots.
info_print "... Enabling snapper service"
systemctl enable snapper-timeline.timer --root=/mnt &>/dev/null
systemctl enable snapper-cleanup.timer --root=/mnt &>/dev/null
systemctl enable grub-btrfsd --root=/mnt &>/dev/null

# Setting umask to 077.
info_print "umask to 077"
sed -i 's/022/077/g' /mnt/etc/profile
echo "" >> /mnt/etc/bash.bashrc
echo "umask 077" >> /mnt/etc/bash.bashrc

# Setting virtual system - if present
virt_check

# Finishing up
intro_print " "
intro_print "Done, you may now wish to reboot (further changes can be done by chrooting into /mnt)."
intro_print "======================================================================================"
exit
 
