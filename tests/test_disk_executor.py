from pure_arch.utils.executor import Executor
from pure_arch.executors.disk import DiskManager

if __name__ == '__main__':
    # Initialize the Executor
    disk_executor = Executor(chroot_path="/mnt")
    # Initialize the Disk manager
    disk_manager = DiskManager(disk_executor)

    print("\n--- Running Disk Operations (Dry Run) ---\n")

    # 1. Disk Clearing / Wiping
    disk_manager.clear_partition_table("/dev/vda")
    disk_manager.wipe_disk("/dev/vda", count=4)

    # 2. Partitioning (Simplified)
    # disk_manager.create_partition("/dev/vda", "1MiB", "+512MiB", type_code="EF00") # EFI
    # disk_manager.create_partition("/dev/vda", "513MiB", "+10G", type_code="8200")  # Swap
    # disk_manager.create_partition("/dev/vda", "10.5GiB", "0", type_code="8300")   # Root

    # 3. Formatting
    disk_manager.format_partition("/dev/vda1", "fat32", label="EFI_SYSTEM")
    disk_manager.format_partition("/dev/vda2", "swap", label="SWAP")
    disk_manager.format_partition("/dev/vda3", "btrfs", label="ARCH_ROOT")

    # 4. LUKS Encryption (Example)
    # NOTE: This is highly simplified and assumes keyfile/non-interactive method or user input is handled.
    # disk_manager.luks_encrypt("/dev/vda4", "cryptroot")
    # disk_manager.luks_open("/dev/vda4", "cryptroot")
    # disk_manager.format_partition("/dev/mapper/cryptroot", "btrfs", label="CRYPT_ROOT")

    # 5. Mounting
    disk_manager.mount_partition("/dev/vda3", "/mnt")
    disk_manager.mount_partition("/dev/vda1", "/mnt/boot", options="defaults,noatime")
    disk_manager.mount_partition("/dev/vda2", "none", options="swap") # Activating swap

    # 6. Btrfs Subvolumes
    disk_manager.create_btrfs_subvolume("/mnt", "@")
    disk_manager.create_btrfs_subvolume("/mnt", "@home")
    disk_manager.unmount_partition("/mnt") # Unmount root for re-mounting subvolumes

    # 7. Final Mount of Subvolumes (requires re-mounting the device itself)
    # Assume /dev/vda3 is the btrfs device
    # disk_manager.mount_partition("/dev/vda3", "/mnt") # Re-mount device
    # disk_manager.mount_btrfs_subvolume("/dev/vda3", "/mnt", "@") # Mount @ over /mnt
    # disk_manager.mount_btrfs_subvolume("/dev/vda3", "/mnt/home", "@home") # Mount @home over /mnt/home

    # 8. Fstab Generation
    # NOTE: This will use the current /mnt structure to generate fstab content.
    disk_manager.generate_fstab()
