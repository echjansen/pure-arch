### === P U R E - A R C H ===
This is a setup script to install a lean and secure version of the Arch Linux operating system either on either a server or laptop.
The total installation time is around 5 minutes, after anwering the basic question of installation disk, user, paswords, keyboard and locale.
Each install script is is a single file and it should be rather straight forward to ammend to your personal needs.

The scripts are inspired by Tommy Trans Arch Setup Script.

### Features
1. Encrypted /boot and /root with LUKS1
2. SUSE - like partition layout
3. Fully working snapper snapshots & rollback
4. Minimal packages (no desktops, etc)
5. AppArmor and Firewalld enabled by default
6. Defaulting umask to 077
7. Randomize Mac Address and disable Connectivity Check for privacy
8. Kernel/grub settings
9. Secure Boot script (after Arch installation)

### How to install?
1. Download an Arch Linux ISO from [here](https://archlinux.org/download/)
2. Flash the ISO onto an [USB Flash Drive](https://wiki.archlinux.org/index.php/USB_flash_installation_medium).
3. Boot the live environment.
4. Connect to the internet.
5. `git clone https://github.com/echjansen/pure-arch/`
6. `cd pure-arch`
7. `./pure-arch-server.sh`, or
8. `./pure-arch-laptopm.sh`

### Partitions layout

| Partition/Subvolume | Label                        | Mountpoint               | Notes                       |
|---------------------|------------------------------|--------------------------|-----------------------------|
| 1                   | ESP                          | /boot/efi                | Unencrypted FAT32           |
| 2                   | @/.snapshots/X/snapshot      | /                        | Encrypted BTRFS             |
| 3                   | @/boot                       | /boot/                   | Encrypted BTRFS (nodatacow) |
| 4                   | @/root                       | /root                    | Encrypted BTRFS             |
| 5                   | @/home                       | /home                    | Encrypted BTRFS             |
| 6                   | @/.snapshots                 | /.snapshots              | Encrypted BTRFS             |
| 7                   | @/srv                        | /srv                     | Encrypted BTRFS (nodatacow) |
| 8                   | @/var_log                    | /var/log                 | Encrypted BTRFS (nodatacow) |
| 9                   | @/var_log/journal            | /var/log/journal         | Encrypted BTRFS (nodatacow) |
| 10                  | @/var_crash                  | /var/crash               | Encrypted BTRFS (nodatacow) |
| 11                  | @/var_cache                  | /var/cache               | Encrypted BTRFS (nodatacow) |
| 12                  | @/var_tmp                    | /var/tmp                 | Encrypted BTRFS (nodatacow) |
| 13                  | @/var_spool                  | /var/spool               | Encrypted BTRFS (nodatacow) |
| 14                  | @/var_lib_libvirt_images     | /var/lib/libvirt/images  | Encrypted BTRFS (nodatacow) |
| 15                  | @/var_lib_machines           | /var/lib/machines        | Encrypted BTRFS (nodatacow) |
| 16                  | @/var_lib_gdm                | /var/lib/gdm             | Encrypted BTRFS (nodatacow) |
| 17                  | @/var_lib_AccountsService    | /var/lib/AccountsService | Encrypted BTRFS (nodatacow) |
| 18                  | @/cryptkey                   | /cryptkey                | Encrypted BTRFS (nodatacow) |

### Snapper behavior
The partition layout uaed allows to replicate the behavior found in openSUSE.
1. Snapper rollback <number> works! You will no longer need to manually rollback from a live USB like you would with the @ and @home layout suggested in the Arch Wiki.
2. You can boot into a readonly snapshot! GDM and other services will start normally so you can get in and verify that everything works before rolling back.
3. Automatic snapshots on pacman install/update/remove operations
4. Directories such as /boot, /boot/efi, /var/log, /var/crash, /var/tmp, /var/spool, /var/lib/libvirt/images are excluded from the snapshots as they either should be persistent or are just temporary files. /cryptkey is excluded as we do not want the encryption key to be included in the snapshots, which could be sent to another device as a backup.
5. GRUB will boot into the default BTRFS snapshot set by snapper. Like on SUSE, your running system will always be a read-write snapshot in @/.snapshots/X/snapshot.

### LUKS1 and Encrypted /boot (Mumbo Jumbo stuff)
This is the same setup that is used on openSUSE. One problem with the way Secure Boot currently works is that the initramfs and a variety of things in /boot are not validated by GRUB whatsoever, even if Secure Boot is active. Thus, they are vulnerable to tampering. The approach as of now is to encrypt the entire /boot partition and have the only file that is unencrypted - the grubx64.efi stub - validated by the firmware.
