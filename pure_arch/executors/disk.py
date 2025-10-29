# pure_arch/executors/disk.py
import os
from typing import TYPE_CHECKING, Optional, Tuple

from pure_arch.utils.executor import Executor
from pure_arch.core import app_logger

# Global constants for mount paths
MOUNT_ROOT = "/mnt"

# Type checking to prevent circular imports if necessary
if TYPE_CHECKING:
    from my_app.config.models import ArchInstallerConfig, Disk, Partition

# Setup the logger
logger = app_logger

class DiskManager:
    """
    Expert class for performing disk and partition management operations
    on a system being prepared for an Arch Linux installation.
    All operations are delegated to the provided Executor instance.
    """

    def __init__(self, executor: Executor):
        """
        Initializes the Disk management class.

        Args:
            executor (Executor): An instance of the Executor class for command execution.
        """
        self.executor = executor
        logger.info("Disk manager initialized.")

    # --- DISK LEVEL OPERATIONS ---

    def wipe_disk(self, device: str, count: int = 1, force: bool = False) -> Tuple[int, str, str]:
        """
        Wipes the beginning of a disk (MBR/GPT) using dd to zero out the first few blocks.
        This is typically used to remove old bootloaders/partition tables.

        Args:
            device (str): The disk device path (e.g., '/dev/sda').
            count (int): The number of blocks (MB) to write (dd's count=). Defaults to 1.
            force (bool): If True, skips confirmation/warnings.

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        # NOTE: Using a block size of 1M for safety and speed. count=1 is 1MB.
        command = [
            "dd", "if=/dev/zero", f"of={device}", "bs=1M", f"count={count}", "status=progress",
        ]
        return self.executor.run(
            description=f"Wiping first {count}MB of disk {device}",
            command=command,
            verbose=True,
            check=True
        )

    def clear_partition_table(self, device: str) -> Tuple[int, str, str]:
        """
        Clears the partition table from a disk device using 'sgdisk -Z'.
        This effectively makes the entire disk unpartitioned.

        Args:
            device (str): The disk device path (e.g., '/dev/sda').

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        command = ["sgdisk", "-Z", device]
        return self.executor.run(
            description=f"Clearing partition table on {device}",
            command=command,
            verbose=True,
            check=True
        )

    # --- PARTITION LEVEL OPERATIONS ---

    def create_partition(self, device: str, start: str, size: str, type_code: str = "8300") -> Tuple[int, str, str]:
        """
        Creates a new GPT partition using sgdisk.

        Args:
            device (str): The disk device path (e.g., '/dev/sda').
            start (str): Start sector/size (e.g., '0', '+1MiB'). Note: 'sgdisk' often prefers '0' for default start.
            size (str): Size/end sector (e.g., '+512M' or '0' for rest of disk).
            type_code (str): GPT partition type code (e.g., 'EF00' for EFI, '8300' for Linux).

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """

        # sgdisk -n {part_num}:{start}:{end} -t {part_num}:{type_code} {device}
        # We use '0' for the partition number, which tells sgdisk to automatically
        # select the next available partition number.
        # We use the provided 'start' and 'size' for the partition boundaries.

        # sgdisk command to create partition and set its type in a single run
        command = [
            "sgdisk",
            f"-n 0:{start}:{size}",  # -n {part_num}:{start}:{end}
            f"-t 0:{type_code}",     # -t {part_num}:{type_code}
            device
        ]

        # NOTE: The sgdisk documentation often implies '0' for start means the first
        # available sector, and '0' for size means the rest of the disk.
        # The variables 'start' and 'size' are used directly as parameters for maximum
        # flexibility, matching the original function's intent.

        return self.executor.run(
            description=f"Creating GPT partition on {device} (Start: {start}, Size: {size}, Type: {type_code}) using sgdisk",
            command=command,
            verbose=True,
            check=True
        )

    def delete_partition(self, device: str, partition_number: int) -> Tuple[int, str, str]:
        """
        Deletes a specific partition on a disk using 'sgdisk -d'.

        Args:
            device (str): The disk device path (e.g., '/dev/sda').
            partition_number (int): The partition number (e.g., 1, 2, 3).

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        # Note: sgdisk renumbers partitions by default on write.
        command = ["sgdisk", f"-d={partition_number}", device]
        return self.executor.run(
            description=f"Deleting partition {partition_number} on {device}",
            command=command,
            verbose=True,
            check=True
        )

    def format_partition(self, partition_path: str, filesystem: str, label: Optional[str] = None) -> Tuple[int, str, str]:
        """
        Formats a partition with a specified filesystem.

        Args:
            partition_path (str): The partition path (e.g., '/dev/sda1').
            filesystem (str): The filesystem type (e.g., 'ext4', 'btrfs', 'fat32').
            label (Optional[str]): An optional label for the filesystem.

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        if filesystem == "ext4":
            fs_cmd = ["mkfs.ext4", "-F"]
            if label: fs_cmd.extend(["-L", label])
        elif filesystem == "btrfs":
            fs_cmd = ["mkfs.btrfs", "-f"]
            if label: fs_cmd.extend(["-L", label])
        elif filesystem == "fat32":
            # Used for EFI system partition
            fs_cmd = ["mkfs.fat", "-F32"]
            if label: fs_cmd.extend(["-n", label])
        elif filesystem == "swap":
            fs_cmd = ["mkswap"]
            if label: fs_cmd.extend(["-L", label])
        else:
            raise ValueError(f"Unsupported filesystem: {filesystem}")

        fs_cmd.append(partition_path)

        return self.executor.run(
            description=f"Formatting {partition_path} as {filesystem}",
            command=fs_cmd,
            verbose=True,
            check=True
        )

    def luks_encrypt(self, partition_path: str, name: str, keyfile_path: Optional[str] = None) -> Tuple[int, str, str]:
        """
        Encrypts a partition using LUKS (cryptsetup luksFormat).
        NOTE: This function requires interactive input for the passphrase,
        which must be handled by the Executor or a non-interactive method (keyfile).

        Args:
            partition_path (str): The partition path (e.g., '/dev/sda3').
            name (str): The device name for the mapped LUKS volume (e.g., 'cryptroot').
            keyfile_path (Optional[str]): Path to a keyfile for non-interactive format.

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        command = ["cryptsetup", "luksFormat", partition_path]
        if keyfile_path:
            command.extend(["--key-file", keyfile_path])
        else:
            # Requires interactive/passphrase handling, which Executor's run might not fully support
            # without additional logic (e.g., expect) or a helper script.
            logger.warning("LUKS format is typically interactive. Ensure Executor/environment can handle password prompts.")

        return self.executor.run(
            description=f"LUKS formatting {partition_path}",
            command=command,
            verbose=True,
            check=True
        )

    def luks_open(self, partition_path: str, name: str, keyfile_path: Optional[str] = None) -> Tuple[int, str, str]:
        """
        Opens a LUKS encrypted partition (cryptsetup luksOpen).

        Args:
            partition_path (str): The partition path (e.g., '/dev/sda3').
            name (str): The desired device name for the mapped LUKS volume (e.g., 'cryptroot').
            keyfile_path (Optional[str]): Path to a keyfile for non-interactive opening.

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        command = ["cryptsetup", "open", partition_path, name]
        if keyfile_path:
            command.extend(["--key-file", keyfile_path])

        return self.executor.run(
            description=f"Opening LUKS volume {name} from {partition_path}",
            command=command,
            verbose=True,
            check=True
        )

    # --- MOUNT/UNMOUNT OPERATIONS ---

    def mount_partition(self, source: str, target: str, options: Optional[str] = None) -> Tuple[int, str, str]:
        """
        Mounts a filesystem/partition to a target directory.
        Ensures the target directory exists before attempting to mount.

        Args:
            source (str): The device or volume to mount (e.g., '/dev/sda1').
            target (str): The mount point (e.g., '/mnt', '/mnt/boot').
            options (Optional[str]): Optional mount options (e.g., 'defaults,noatime').

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr) of the mount command.
                                  Raises an exception via check=True if directory creation fails.
        """

        # 1. Ensure the target directory exists.
        # This is a critical step for a reliable mount operation.
        if not os.path.isdir(target):
            # Using mkdir -p ensures all parent directories are created
            # and it doesn't fail if the directory already exists (though we checked).
            mkdir_command = ["mkdir", "-p", target]

            # Execute directory creation. We check this strictly.
            self.executor.run(
                description=f"Ensuring mount target directory {target} exists",
                command=mkdir_command,
                verbose=False,
                check=True  # Ensure creation succeeds before proceeding to mount
            )

        # 2. Prepare the mount command.
        command = ["mount"]
        if options:
            command.extend(["-o", options])

        command.extend([source, target])

        # 3. Execute the mount command.
        return self.executor.run(
            description=f"Mounting {source} to {target} (Options: {options or 'default'})",
            command=command,
            verbose=True,
            check=True
        )

    def unmount_partition(self, target_or_source: str) -> Tuple[int, str, str]:
        """
        Unmounts a filesystem/partition from a target directory or source device.

        Args:
            target_or_source (str): The mount point (e.g., '/mnt/boot') or the device (e.g., '/dev/sda1').

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        command = ["umount", target_or_source]
        return self.executor.run(
            description=f"Unmounting {target_or_source}",
            command=command,
            verbose=True,
            check=True
        )

    # --- BTRFS SPECIFIC OPERATIONS ---

    def create_btrfs_subvolume(self, mount_point: str, subvolume_path: str) -> Tuple[int, str, str]:
        """
        Creates a Btrfs subvolume. Requires the filesystem to be mounted first.

        Args:
            mount_point (str): The temporary mount point of the Btrfs root filesystem (e.g., '/mnt').
            subvolume_path (str): The path to the new subvolume (e.g., '@', '@home').

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        full_path = os.path.join(mount_point, subvolume_path)
        command = ["btrfs", "subvolume", "create", full_path]
        return self.executor.run(
            description=f"Creating Btrfs subvolume: {subvolume_path} at {mount_point}",
            command=command,
            verbose=True,
            check=True
        )

    def mount_btrfs_subvolume(self, source: str, target: str, subvolume_name: str, options: Optional[str] = "defaults,noatime,compress=zstd") -> Tuple[int, str, str]:
        """
        Mounts a Btrfs subvolume.

        Args:
            source (str): The device or volume of the Btrfs filesystem (e.g., '/dev/sda3').
            target (str): The final mount point (e.g., '/mnt/').
            subvolume_name (str): The name of the subvolume (e.g., '@', '@home').
            options (Optional[str]): Optional mount options.

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        full_options = f"subvol={subvolume_name},{options}" if options else f"subvol={subvolume_name}"
        return self.mount_partition(source=source, target=target, options=full_options)

    # --- FSTAB GENERATION ---

    def generate_fstab(self, target_path: str = "/mnt/etc/fstab", append: bool = False, use_uuid: bool = True) -> Tuple[int, str, str]:
        """
        Generates an fstab file for the newly installed system.

        Args:
            target_path (str): The path to write the fstab file (usually '/mnt/etc/fstab').
            append (bool): If True, appends to the file, otherwise overwrites.
            use_uuid (bool): If True, uses UUIDs; otherwise, uses device names.

        Returns:
            Tuple[int, str, str]: (exit_code, stdout, stderr).
        """
        if use_uuid:
            genfstab_opts = "-U" # Use UUIDs
        else:
            genfstab_opts = "-L" # Use Labels

        redirect = ">>" if append else ">"

        # The command executes outside the chroot (no chroot=True)
        # and pipes the output to tee to write to the target file inside /mnt.
        # It's safest to use tee with shell=True/a string command here.
        command = f"genfstab {genfstab_opts} /mnt {redirect} {target_path}"

        # Note: Setting shell=True for the pipe/redirection to work seamlessly
        return self.executor.run(
            description=f"Generating fstab to {target_path} (UUIDs: {use_uuid})",
            command=command,
            chroot=False,
            shell=True,
            verbose=True,
            check=True
        )
