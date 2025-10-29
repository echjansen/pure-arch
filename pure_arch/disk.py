from typing import Optional, List
import os
import sys
from pathlib import Path

# Local imports (assuming these exist and are correctly implemented)
from pure_arch.utils.executor import Executor, ShellCommandError
from pure_arch.config.models import ArchInstallerConfig, Disk, Partition
from pure_arch import core
from pure_arch.utils.logger import initialize_app_logger


# NOTE: Placeholder method for demonstration.
# You MUST implement a secure way to get the password from your config model.
# e.g., ArchInstallerConfig.get_luks_password()
def _get_luks_password_placeholder(config: ArchInstallerConfig) -> Optional[str]:
    """Retrieves the LUKS password from the config or a secure source."""
    # This should be replaced with actual secure secret retrieval logic
    # For now, we'll return a placeholder string or None if not set.
    # Assuming config.luks_password is set securely elsewhere
    # return config.luks_password
    return "123" # Replace this with your actual retrieval logic


def prepare_disk(executor: Executor, config: ArchInstallerConfig, dry_run: bool = False):
    """
    Performs disk preparation, non-interactive LUKS encryption, BTRFS filesystem creation,
    and the final subvolume mounting sequence based on the configuration model.

    Args:
        executor: An initialized Executor instance for command execution.
        config: The loaded ArchInstallerConfig model instance.
        dry_run: If True, commands are logged but not executed.
    """

    # --------------------------------------------------------------------------
    # 1. Configuration Validation and Extraction
    # --------------------------------------------------------------------------
    if not config.disk:
        executor.logger.critical("Configuration error: No disks defined in config.")
        raise ValueError("Configuration requires at least one disk.")

    target_disk: Disk = config.disk[0]

    efi_config: Optional[Partition] = None
    root_config: Optional[Partition] = None

    # Locate the EFI and ROOT partitions
    for p in target_disk.partition:
        if p.filesystem in ("fat32", "vfat"):
            efi_config = p
        elif p.crypt and p.filesystem == "btrfs":
            root_config = p

    if not (efi_config and root_config and root_config.btrfssubvolumes):
        executor.logger.critical("Configuration error: Missing EFI partition, encrypted BTRFS ROOT, or BTRFS subvolumes.")
        raise ValueError("Disk config is incomplete for LUKS+BTRFS setup.")

    # --- LUKS Password Retrieval ---
    luks_password = _get_luks_password_placeholder(config)
    if not luks_password and not dry_run:
         executor.logger.critical("LUKS password not available. Cannot proceed with non-interactive encryption.")
         raise ValueError("LUKS password is required for non-interactive setup.")

    # Device definitions
    target_device = target_disk.path
    efi_part = f"{target_device}{efi_config.number}"
    root_part = f"{target_device}{root_config.number}"
    luks_device = f"/dev/mapper/{root_config.cryptname or 'linuxroot'}"

    executor.logger.info(f"Starting disk preparation on configured device: {target_device}")

    try:
        # --------------------------------------------------------------------------
        # 2. Partitioning (sgdisk)
        # --------------------------------------------------------------------------
        if target_disk.wipe:
             executor.run(
                description=f"Wiping existing partitions and partition table on {target_device}",
                command=f"sgdisk -Z {target_device}",
                dryrun=dry_run
            )

        # Dynamic Partition Creation
        sgdisk_commands = []
        for p in target_disk.partition:
            # -n<number>:<start>:<end> -t<number>:<guid> -c<number>:<name>
            sgdisk_commands.extend([
                f"-n{p.number}:{p.start or '0'}:{p.size}",
                f"-t{p.number}:{p.guid or p.type}",
                f"-c{p.number}:{p.label}"
            ])

        executor.run(
            description=f"Creating partitions based on config",
            command=["sgdisk"] + sgdisk_commands + [target_device],
            dryrun=dry_run
        )

        executor.run(
            description=f"Updating kernel partition table",
            command=f"partprobe -s {target_device}",
            dryrun=dry_run
        )

        # --------------------------------------------------------------------------
        # 3. LUKS Encryption and Filesystem Creation (Non-Interactive)
        # --------------------------------------------------------------------------

        crypt_type = root_config.crypttype or "luks2"
        crypt_label_arg = f"--label={root_config.cryptlabel}" if root_config.cryptlabel else ""

        # LUKS Format: Use printf pipe for non-interactive formatting
        luks_format_command = f"""
            printf "{luks_password}" | cryptsetup --batch-mode luksFormat
            --type={crypt_type} {crypt_label_arg} {root_part}
        """

        executor.run(
            description=f"Encrypting root partition {root_part} with {crypt_type} (Non-Interactive)",
            # NOTE: Assumes Executor can run this complex pipe command string with shell=True
            command=luks_format_command,
            dryrun=dry_run,
            capture_output=False
        )

        # LUKS Open: Use printf pipe for non-interactive opening
        luks_open_command = f"""
            printf "{luks_password}" | cryptsetup luksOpen
            {root_part} {root_config.cryptname or 'linuxroot'}
        """

        executor.run(
            description=f"Opening LUKS volume as {luks_device} (Non-Interactive)",
            # NOTE: Assumes Executor can run this complex pipe command string with shell=True
            command=luks_open_command,
            dryrun=dry_run,
            capture_output=False
        )

        # EFI Filesystem
        executor.run(
            description=f"Creating {efi_config.filesystem.upper()} filesystem on EFI partition {efi_part}",
            command=["mkfs.vfat", "-F32", "-n", efi_config.label, efi_part],
            dryrun=dry_run
        )

        # BTRFS Filesystem
        executor.run(
            description=f"Creating BTRFS filesystem on LUKS volume {luks_device}",
            command=["mkfs.btrfs", "-f", "-L", root_config.cryptlabel or "linuxroot", luks_device],
            dryrun=dry_run
        )

        # --------------------------------------------------------------------------
        # 4. Initial BTRFS Mounting and Subvolume Creation
        # --------------------------------------------------------------------------

        # a. Initial Mount (mount the BTRFS volume itself)
        executor.run(
            description=f"Mounting BTRFS volume {luks_device} to /mnt for subvolume creation",
            command=["mount", luks_device, "/mnt"],
            dryrun=dry_run
        )

        # b. Create BTRFS subvolumes (naming them @<name>)
        # Subvolumes list includes the root subvolume ('@') and cleaned named subvolumes.
        # Ensure subvolume names are cleaned of leading/trailing slashes for @<name> creation.
        cleaned_subvols = [s.strip('/').lstrip('@') for s in root_config.btrfssubvolumes if s.strip()]
        subvolumes_to_create: List[str] = ["@"] + [s for s in cleaned_subvols if s != '']

        for name in set(subvolumes_to_create): # Use set to avoid duplicates
            is_root = name == "@"
            # Path inside the temporary /mnt mount point: /mnt/@ or /mnt/@home
            subvol_path = "/mnt/@" if is_root else f"/mnt/@{name}"

            executor.run(
                description=f"Creating BTRFS subvolume @{name}",
                command=["btrfs", "subvolume", "create", subvol_path],
                dryrun=dry_run
            )

        # --------------------------------------------------------------------------
        # 5. Unmount and Final Remounting with Subvolumes (Crucial Step)
        # --------------------------------------------------------------------------
        executor.run(
            description="Unmounting /mnt to prepare for subvolume remounting",
            command=["umount", "/mnt"],
            dryrun=dry_run
        )

        # a. Remount the main root subvolume (@) to /mnt
        btrfs_options = root_config.btrfsoptions or "noatime,compress=zstd"
        root_mount_options = f"{btrfs_options},subvol=@"

        executor.run(
            description=f"Remounting BTRFS root subvolume to /mnt with options: {root_mount_options}",
            command=["mount", "-o", root_mount_options, luks_device, "/mnt"],
            dryrun=dry_run
        )

        # b. Create directories and mount the rest of the named subvolumes
        for subvol_raw_name in root_config.btrfssubvolumes:
            subvol_name = subvol_raw_name.strip('/').lstrip('@') # Ensure clean name for path

            # Skip if the cleaned name resolves to the root mount point (already mounted)
            if subvol_name.strip() == "":
                continue

            # Mount path must be /mnt/<subvol_name> (e.g., /mnt/var, /mnt/home)
            mount_path = os.path.join("/mnt", subvol_name)

            # Create the final destination directory
            executor.run(
                description=f"Creating destination directory {mount_path}",
                command=["mkdir", "-p", mount_path],
                dryrun=dry_run
            )

            # Mount the subvolume (using the cleaned name for the subvol=@<name> option)
            subvol_mount_options = f"{btrfs_options},subvol=@{subvol_name}"
            executor.run(
                description=f"Mounting subvolume @{subvol_name} to {mount_path}",
                command=["mount", "-o", subvol_mount_options, luks_device, mount_path],
                dryrun=dry_run
            )

        # c. Mount the EFI Partition
        efi_mount_point = f"/mnt{efi_config.path}"

        executor.run(
            description=f"Creating EFI mount point {efi_mount_point}",
            command=["mkdir", "-p", efi_mount_point],
            dryrun=dry_run
        )
        executor.run(
            description=f"Mounting EFI partition {efi_part} to {efi_mount_point}",
            command=["mount", "-o", "uid=0,gid=0,umask=077", efi_part, efi_mount_point],
            dryrun=dry_run
        )

    except ShellCommandError as e:
        executor.logger.critical(f"FATAL ERROR during disk preparation. The operation failed at command: '{e.command}'")
        executor.logger.critical("Review the logs for full details. Attempting emergency cleanup.")
        cleanup_mounts(executor, dry_run=dry_run)
        raise

# --------------------------------------------------------------------------
# Cleanup Function
# --------------------------------------------------------------------------

def cleanup_mounts(executor: Executor, dry_run: bool):
    """Attempt to unmount and close LUKS devices in case of failure."""
    executor.logger.warning("Attempting emergency cleanup of mounted partitions.")
    try:
        # Attempt to unmount all mounted subvolumes and efi
        executor.run("Unmounting all recursively from /mnt", ["umount", "-R", "/mnt"], dryrun=dry_run, check=False)

        # Close the LUKS volume (using the hardcoded default name as a safe fallback)
        executor.run("Closing LUKS volume 'linuxroot'", ["cryptsetup", "luksClose", "linuxroot"], dryrun=dry_run, check=False)
    except Exception as e:
        executor.logger.error(f"Cleanup failed with an unexpected error: {e}", exc_info=True)

# --------------------------------------------------------------------------
# Example Usage (Standalone Execution)
# --------------------------------------------------------------------------

if __name__ == "__main__":

    # 1. Correct the CONFIG_PATH calculation: Go up one directory (to the project root)
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_PATH = script_dir.parent / 'config.toml'

    # 2. Initialize Logger
    if core.app_logger is None:
        core.app_logger = initialize_app_logger(app_name="ArchSetup")

    try:
        # 3. Load Config
        config_data = ArchInstallerConfig.load_config_from_file(CONFIG_PATH)

        # 4. Initialize Executor
        exe = Executor(logger_instance=core.app_logger, chroot_path="/mnt")

        # 5. Run the disk preparation (Set dry_run=True for safety during testing)
        core.app_logger.info(config_data.display_summary())
        core.app_logger.warning("Running in DRY-RUN mode. Change 'dry_run' to False to execute.")

        prepare_disk_from_config(executor=exe, config=config_data, dry_run=True)

    except (ValueError, FileNotFoundError, Exception) as e:
        core.app_logger.critical(f"Setup terminated due to initialization error: {e}")
        sys.exit(1)
