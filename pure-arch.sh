#!/bin/bash
set -e                          # Exit on error

# Terminal UI functions
source lib/pure-linux-tui.sh

# Default Configuration File
CONFIG_FILE="config.conf"

# Log files
LOG_COMMANDS="logs/commands.log"  # Log file for commands executed
LOG_ERRORS="logs/error.log"       # Log file for errors

# Global Variables
DEBUG=0                         # 1=Debug is active
VERBOSE=0                       # 1=Show shell execution output
DRYRUN=0                        # 1=Do net execute to shell commands

# Global constants
readonly MOUNT_POINT="/tmp"     # Mount point for Arch Linux installation
readonly LUKS_NAME="root"       # 'root' is required by the Discoverable Partitions Specifications

# Hardware Detection Global Variables
HARDWARE_CPU=""                 # Intel, AMD, Unknown
HARDWARE_GPU=""                 # Intel, AMD, NVIDIA, Basic, None, Intel+NVIDIA, AMD+NVIDIA, etc.
HARDWARE_3D=""                  # True, False, Limited
HARDWARE_VIRTUAL=""             # None, VMware, VirtualBox, QEMU/KVM, Hyper-V, Xen, Parallels

# Default Configuration Variables
DISK_TARGET="/dev/sdb"
PART_EFI_PATH=""                # Variable validation will set
PART_EFI_SIZE="1024MiB"
PART_ROOT_PATH=""               # Variable validation will set
PART_ROOT_SIZE="50GiB"
PART_ROOT_FS="btrfs"
PART_ROOT_FS_BTRFS_OPTIONS="rw,noatime,compress-force=zstd:1,space_cache=v2"
PART_HOME_PATH=""               # Variable validation will set
SWAP_SIZE_MB="8192"
FB_LOCALE="en_US.UTF-8"         # Firstboot variables
FB_COUNTRY="Australia"
FB_TIMEZONE="Australia/Victoria"
FB_KEYMAP="us"
FONT="ter-v16b"
HOST_NAME="archlinux"
USER_NAME="echjansen"
USER_PASSWORD=""
USER_PASS_HASHED=""
USER_SHELL="/bin/bash"
ROOT_PASS_HASHED=""
LUKS_PASSWORD=""
BOOTLOADER="systemd-boot"
PACKAGES_BASE=()
PACKAGES_UTILS=()
PACKAGES_HARDWARE=()

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_CONFIG_ERROR=1
readonly EXIT_COMMAND_ERROR=3
readonly EXIT_PERMISSION_ERROR=10
readonly EXIT_SYSTEM_ERROR=11
readonly EXIT_NETWORK_ERROR=12
readonly EXIT_DISK_ERROR=13
readonly EXIT_DEPENDENCY_ERROR=14

## Error trapping and clean-up
# Set up trap EARLY - before any risky operations
trap cleanup_error ERR EXIT

### = cleanup_error: Close encrypted partitions, umount, etc
function cleanup_error() {
    local exit_code=$?

    # Only run cleanup if there was an actual error (from 'run' calling exit)
    if [[ $exit_code -ne 0 ]]; then
        tui_print_message "Installation failed with exit code $exit_code. Cleaning up..."

        # Print last lines from error log
        if [[ -n "$LOG_ERRORS" ]]; then
            echo ""
            tui_print_title "[ ERROR LOG PREVIEW ]" "$RED"
            tail -n 10 "$LOG_ERRORS"
            tui_print_title "[ END LOG PREVIEW ]" "$RED"
            echo ""
            tui_print_message "Check $LOG_ERRORS for full details." "$YELLOW$BOLD" "-->"
        fi
    fi
}

### = cleanup: Cleanup potential creations
function cleanup() {

    # Cleanup operations
    run "umount --lazy /dev/mapper/${LUKS_NAME}"
    run "cryptsetup close -q ${LUKS_NAME}"
    run "umount -R -q ${MOUNT_POINT}"

    # Cleanup logs
    run "rm -rf logs/"
}

## TUI Functions
### = input_info: display messages prompting for input in bold yellow
function input_info() {
    # The message is printed using '-n -e' to allow escape codes
    # and to keep the cursor on the same line (no automatic newline).
    echo -n -e "$BOLD$YELLOW[INPUT]${RESET} $1" >&2
}

## Check functions
# Here is a collection of checks that validate if the target system is suitable for installation.

### = check_root_priviledges: Check if running as root
function check_root_privileges() {
    if [[ $EUID -ne 0 ]]; then
        tui_print_message "This script must be run as root for Arch installation" "$RED" "$PREFIX_FAILURE"
        tui_print_message "Please run: sudo $0" "$YELLOW" "-->"
        exit $EXIT_PERMISSION_ERROR
    fi
    tui_print_message "Running with root privileges" "$GREEN" "$PREFIX_SUCCESS"
}

### = check_arch_iso: Check if booted from Arch ISO
function check_arch_iso() {
    if [[ ! -f /etc/arch-release ]]; then
        tui_print_message "Not running on Arch Linux" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_SYSTEM_ERROR
    fi

    # Check if running from live environment
    if ! grep -q "archiso" /proc/cmdline 2>/dev/null; then
        tui_print_message "Not running from Arch ISO - proceeding anyway" "$YELLOW" "$PREFIX_WARNING"
    else
        tui_print_message "Running from Arch ISO live environment" "$GREEN" "$PREFIX_SUCCESS"
    fi
}

### = check_ufi_mode: Check if running in UEFI mode
function check_uefi_mode() {
    if [[ -d /sys/firmware/efi/efivars ]]; then
        tui_print_message "System booted in UEFI mode" "$GREEN" "$PREFIX_SUCCESS"

        # Verify EFI variables are writable
        if [[ ! -w /sys/firmware/efi/efivars ]]; then
            tui_print_message "EFI variables directory is not writable" "YELLOW" "$PREFIX_WARNING"
        fi
    else
        tui_print_message "System not booted in UEFI mode" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_SYSTEM_ERROR
    fi
}

### = check_internet_connectivity: Check internet connectivity
function check_internet_connectivity() {
    display_info "Checking internet connectivity..."

    # Test DNS resolution
    if ! nslookup archlinux.org &>/dev/null; then
        display_critical "DNS resolution failed"
        exit $EXIT_NETWORK_ERROR
    fi

    # Test connection to Arch mirrors
    local test_urls=("archlinux.org" "mirror.rackspace.com" "mirrors.kernel.org")
    local connected=false

    for url in "${test_urls[@]}"; do
        if ping -c 2 -W 5 "$url" &>/dev/null; then
            connected=true
            display_completed "Internet connectivity verified via $url"
            break
        fi
    done

    if [[ "$connected" == false ]]; then
        display_critical "No internet connection available"
        display_info "Please check your network configuration"
        exit $EXIT_NETWORK_ERROR
    fi

    # Test HTTPS connectivity (for pacman)
    if ! curl -s --connect-timeout 10 https://archlinux.org > /dev/null; then
        display_warning "HTTPS connectivity test failed - may cause issues with pacman"
    fi
}

### = check_disk_space: Check disk space requirements
function check_disk_space() {
    local required_space_gb=15  # Minimum 15GB for base installation

    if [[ ! -b "$DISK_TARGET" ]]; then
        tui_print_message "Target disk $DISK_TARGET not found - skipping disk space check" "$YELLOW" "$PREFIX_WARNING"
        return 0
    fi

    # Get disk size in GB
    local disk_size_bytes
    disk_size_bytes=$(lsblk -b -d -n -o SIZE "$DISK_TARGET" 2>/dev/null)

    if [[ -z "$disk_size_bytes" ]]; then
        tui_print_message "Could not determine disk size for $DISK_TARGET" "$YELLOW" "$PREFIX_WARNING"
        return 0
    fi

    local disk_size_gb=$((disk_size_bytes / 1024 / 1024 / 1024))

    if [[ $disk_size_gb -lt $required_space_gb ]]; then
        tui_print_message "Insufficient disk space: ${disk_size_gb}GB available, ${required_space_gb}GB required" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_DISK_ERROR
    fi

    tui_print_message "Sufficient disk space available: ${disk_size_gb}GB" "$GREEN" "$PREFIX_SUCCESS"
}

### = check_target_disk: Check target disk exists and is accessible
function check_target_disk() {
    if [[ ! -b "$DISK_TARGET" ]]; then
        tui_print_message "Target disk $DISK_TARGET does not exist or is not a block device" "$RED" "$PREFIX_FAILURE"
        tui_print_message "Available disks:" "$YELLOW"
        lsblk -d -o NAME,SIZE,TYPE | grep disk
        exit $EXIT_DISK_ERROR
    fi

    # Check if disk is writable
    if [[ ! -w "$DISK_TARGET" ]]; then
        tui_print_message "Target disk $DISK_TARGET is not writable" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_DISK_ERROR
    fi

    # Warn if disk contains existing partitions
    if lsblk -n "$DISK_TARGET" | grep -q part; then
        tui_print_message "Target disk $DISK_TARGET contains existing partitions" "$YELLOW" "$PREFIX_WARNING"
        tui_print_message "Existing partition layout:" "$YELLOW"
        lsblk "$DISK_TARGET"

        if [[ "$DRYRUN" -eq 0 ]]; then
            input_info "Continue and DESTROY all data on $DISK_TARGET? [y/N]: "
            read -r confirm
            if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                tui_print_message "Installation cancelled by user" "$YELLOW"
                exit 0
            fi
        fi
    fi

    tui_print_message "Target disk $DISK_TARGET validated" "$GREEN" "$PREFIX_SUCCESS"
}

### = check_required_tools: Check all required tools are available
function check_required_tools() {
    local required_tools=(
        "pacman"           # Package manager
        "pacstrap"         # Install packages to new root
        "genfstab"         # Generate fstab
        "arch-chroot"      # Chroot into new installation
        "fdisk"            # Disk partitioning
        "mkfs.fat"         # FAT filesystem (EFI)
        "mkswap"           # Swap creation
        "cryptsetup"       # LUKS encryption
        "curl"             # Download tools
        "timedatectl"      # Time synchronization
    )

    # Add filesystem-specific tools based on ROOT_FS_TYPE
    case "$PART_ROOT_FS" in
        "btrfs")
            required_tools+=("mkfs.btrfs" "btrfs")
            ;;
        "ext4")
            required_tools+=("mkfs.ext4" "e2fsck")
            ;;
        "xfs")
            required_tools+=("mkfs.xfs" "xfs_repair")
            ;;
    esac

    local missing_tools=()

    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing_tools+=("$tool")
        fi
    done

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        tui_print_message "Missing required tools: ${missing_tools[*]}" "$RED" "$PREFIX_FAILURE"
        tui_print_message "Please install missing tools or boot from a complete Arch ISO" "$YELLOW" "-->"
        exit $EXIT_DEPENDENCY_ERROR
    fi

    tui_print_message "All required tools are available" "$GREEN" "$PREFIX_SUCCESS"
}

### = check_system_clock: Check system clock synchronization
function check_system_clock() {

    # Enable NTP synchronization
    if ! timedatectl set-ntp true 2>/dev/null; then
        tui_print_message "Could not enable NTP synchronization" "$YELLOW" "$PREFIX_WARNING"
    fi

    # Wait a moment for sync attempt
    sleep 2

    # Check if time is synchronized
    if timedatectl status | grep -q "System clock synchronized: yes"; then
        tui_print_message "System clock is synchronized" "$GREEN" "$PREFIX_SUCCESS"
    else
        tui_print_message "System clock may not be synchronized" "$YELLOW" "$PREFIX_WARNING"
        tui_print_message "Current time: $(date)" "$YELLOW" "-->"
        tui_print_message "This may cause issues with package signatures" "$YELLOW" "-->"
    fi

    # Verify timezone setting
    FB_TIMEZONE=$(timedatectl show -p Timezone --value)
    tui_print_message "Current timezone: ${FB_TIMEZONE}" "$GREEN" "$PREFIX_SUCCESS"
}

### = check_memory: Check memory requirements
function check_memory() {
    local required_mem_mb=1024  # 1GB minimum for comfortable installation

    # Get available memory in MB
    local available_mem_mb
    available_mem_mb=$(free -m | awk '/^Mem:/ {print $7}')

    if [[ -z "$available_mem_mb" ]]; then
        # Fallback to total memory if available memory detection fails
        available_mem_mb=$(free -m | awk '/^Mem:/ {print $2}')
        tui_print_message "Using total memory for check: ${available_mem_mb}MB" "$YELLOW" "$PREFIX_WARNING"
    fi

    if [[ $available_mem_mb -lt $required_mem_mb ]]; then
        tui_print_message "Low memory: ${available_mem_mb}MB available, ${required_mem_mb}MB recommended" "$YELLOW" "$PREFIX_WARNING"
        tui_print_message "Installation may be slow or fail with insufficient memory" "$YELLOW" "-->"
    else
        tui_print_message "Sufficient memory available: ${available_mem_mb}MB" "$GREEN" "$PREFIX_SUCCESS"
    fi
}

### = check_disk_mounted: Check if target disk is currently mounted (safety check)
function check_disk_mounted() {
    local mounted_partitions
    mounted_partitions=$(lsblk -n -o MOUNTPOINT "$DISK_TARGET" 2>/dev/null | grep -v '^$' || true)

    if [[ -n "$mounted_partitions" ]]; then
        tui_print_message "Target disk $DISK_TARGET has mounted partitions:" "$YELLOW" "$PREFIX_WARNING"
        lsblk "$DISK_TARGET" | grep -E "(MOUNTPOINT|/)"

        if [[ "$DRYRUN" -eq 0 ]]; then
            tui_print_message "These will be unmounted during installation" "$YELLOW" "-->"
        fi
    else
        tui_print_message "Target disk $DISK_TARGET is not currently mounted" "$GREEN" "$PREFIX_SUCCESS"
    fi
}

### = check_all: Perform all checks
function preflight_checks() {
    tui_print_section "Running pre-flight checks..."

    # Check if running as root (required for installation)
    check_root_privileges

    # Check if booted from Arch ISO
    check_arch_iso

    # Check if running in UEFI mode
    check_uefi_mode

    # Check internet connectivity
    # TODO - uncheck
    #check_internet_connectivity

    # Validate all required tools are available
    check_required_tools

    # Check system clock synchronization
    check_system_clock

    # Verify memory requirements
    check_memory

    # Check if target disk is mounted (safety check)
    check_disk_mounted

    # Verify disk space requirements
    check_disk_space

    # Validate target disk exists and is accessible
    check_target_disk

    tui_print_message "All pre-flight checks passed successfully" "$GREEN" "$PREFIX_SUCCESS"

    echo ""
}

## Hardware functions

### = detect_hardware: - Detect hardware and set HARDWARE_x variables
function detect_hardware() {
    local cpu_vendor="Unknown"
    local gpu_vendors=()
    local has_3d="False"
    local virtual_platform="None"
    local packages_hardware=()

    # === CPU DETECTION ===
    if command -v lscpu &>/dev/null; then
        local cpu_vendor_id=$(lscpu | grep "Vendor ID" | awk '{print $3}' 2>/dev/null)
    else
        local cpu_vendor_id=$(awk -F: '/vendor_id/ {print $2; exit}' /proc/cpuinfo | tr -d ' ')
    fi

    case "$cpu_vendor_id" in
        "GenuineIntel")
            cpu_vendor="Intel"
            packages_hardware+=("intel-ucode")
            ;;
        "AuthenticAMD")
            cpu_vendor="AMD"
            packages_hardware+=("amd-ucode")
            ;;
        *)
            cpu_vendor="Unknown"
            ;;
    esac

    # Set global CPU variable
    HARDWARE_CPU="$cpu_vendor"

    # === VIRTUAL MACHINE DETECTION ===
    local vm_indicators=()

    # Check DMI/SMBIOS
    if [[ -f /sys/class/dmi/id/sys_vendor ]]; then
        local sys_vendor=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)
        local product_name=$(cat /sys/class/dmi/id/product_name 2>/dev/null)

        case "$sys_vendor $product_name" in
            *"VMware"*) vm_indicators+=("VMware") ;;
            *"VirtualBox"*) vm_indicators+=("VirtualBox") ;;
            *"QEMU"*) vm_indicators+=("QEMU/KVM") ;;
            *"Microsoft Corporation"*"Virtual Machine"*) vm_indicators+=("Hyper-V") ;;
            *"Xen"*) vm_indicators+=("Xen") ;;
            *"Parallels"*) vm_indicators+=("Parallels") ;;
        esac
    fi

    # Check hypervisor flag in CPU
    if grep -q "hypervisor" /proc/cpuinfo 2>/dev/null; then
        if [[ ${#vm_indicators[@]} -eq 0 ]]; then
            vm_indicators+=("Unknown-VM")
        fi
    fi

    # Check PCI devices for VM indicators
    local pci_vm=$(lspci 2>/dev/null | grep -E "(VMware|VirtualBox|QEMU|Red Hat.*Virtio)" | head -1)
    if [[ -n "$pci_vm" ]]; then
        case "$pci_vm" in
            *"VMware"*) vm_indicators+=("VMware") ;;
            *"VirtualBox"*) vm_indicators+=("VirtualBox") ;;
            *"QEMU"*|*"Red Hat"*) vm_indicators+=("QEMU/KVM") ;;
        esac
    fi

    # Determine primary virtual platform
    if [[ ${#vm_indicators[@]} -gt 0 ]]; then
        virtual_platform="${vm_indicators[0]}"

        # Add VM-specific packages
        case "$virtual_platform" in
            "VMware")
                packages_hardware+=("open-vm-tools" "xf86-video-vmware")
                ;;
            "VirtualBox")
                packages_hardware+=("virtualbox-guest-utils" "xf86-video-vesa")
                ;;
            "QEMU/KVM")
                packages_hardware+=("qemu-guest-agent" "xf86-video-qxl")
                ;;
            "Hyper-V")
                packages_hardware+=("hyperv")
                ;;
        esac
    else
        virtual_platform="None"
    fi

    # Set global Virtual variable
    HARDWARE_VIRTUAL="$virtual_platform"

    # === GPU DETECTION ===
    local gpu_list=()
    local has_discrete_gpu=false

    while IFS= read -r line; do
        case "$line" in
            *"NVIDIA"*|*"GeForce"*|*"Quadro"*|*"Tesla"*)
                if [[ ! " ${gpu_vendors[*]} " =~ " NVIDIA " ]]; then
                    gpu_vendors+=("NVIDIA")
                    gpu_list+=("NVIDIA")
                    has_discrete_gpu=true
                    # Note: NVIDIA drivers often need post-install configuration
                    # hardware_packages+=("nvidia" "nvidia-utils")
                fi
                ;;
            *"AMD"*|*"ATI"*|*"Radeon"*)
                if [[ ! " ${gpu_vendors[*]} " =~ " AMD " ]]; then
                    gpu_vendors+=("AMD")
                    gpu_list+=("AMD")
                    has_discrete_gpu=true
                    packages_hardware+=("mesa" "xf86-video-amdgpu")
                fi
                ;;
            *"Intel"*|*"HD Graphics"*|*"UHD Graphics"*|*"Iris"*)
                if [[ ! " ${gpu_vendors[*]} " =~ " Intel " ]]; then
                    gpu_vendors+=("Intel")
                    gpu_list+=("Intel")
                    packages_hardware+=("mesa" "xf86-video-intel")
                fi
                ;;
            *"Cirrus"*|*"ASPEED"*|*"Matrox"*|*"VMware"*)
                if [[ ! " ${gpu_vendors[*]} " =~ " Basic " ]]; then
                    gpu_vendors+=("Basic")
                    gpu_list+=("Basic")
                    packages_hardware+=("xf86-video-vesa")
                fi
                ;;
        esac
    done < <(lspci | grep -E "(VGA|3D|Display)" 2>/dev/null)

    # Default to None if no GPU detected
    if [[ ${#gpu_vendors[@]} -eq 0 ]]; then
        gpu_vendors=("None")
        gpu_list=("None")
    fi

    # Create GPU string and set global variable
    local gpu_string
    if [[ ${#gpu_list[@]} -gt 1 ]]; then
        # Multiple GPUs - join with +
        IFS='+' gpu_string="${gpu_list[*]}"
    else
        gpu_string="${gpu_list[0]}"
    fi
    HARDWARE_GPU="$gpu_string"

    # === 3D ACCELERATION DETECTION ===
    if [[ "$virtual_platform" == "None" ]] && [[ "$has_discrete_gpu" == true ]]; then
        has_3d="True"
        packages_hardware+=("mesa-utils")
    elif [[ "$virtual_platform" == "None" ]] && [[ " ${gpu_vendors[*]} " =~ " Intel " ]]; then
        has_3d="True"
        packages_hardware+=("mesa-utils")
    elif [[ "$virtual_platform" != "None" ]]; then
        # VM 3D support varies
        case "$virtual_platform" in
            "VMware"|"VirtualBox"|"QEMU/KVM")
                has_3d="Limited"
                ;;
            *)
                has_3d="False"
                ;;
        esac
    else
        has_3d="False"
    fi

    # Set global 3D variable
    HARDWARE_3D="$has_3d"

    # === WRITE PACKAGE FILE ===
    {
        echo "# Hardware Detection Results"
        echo "# Generated: $(date)"
        echo "# CPU: $HARDWARE_CPU"
        echo "# GPU: $HARDWARE_GPU"
        echo "# 3D: $HARDWARE_3D"
        echo "# Virtual: $HARDWARE_VIRTUAL"
        echo ""
        echo "# Hardware-specific packages:"
        for package in "${packages_hardware[@]}"; do
            echo "$package"
        done
    } > PACKAGES_HARDWARE

    return 0
}

### = is_virtual_machine: - is virtual
function is_virtual_machine() {
    [[ "$HARDWARE_VIRTUAL" != "None" ]]
}

### = is_nvidea_gpu: - GPU is nvidea
function is_nvidea_gpu() {
    [[ "$HARDWARE_GPU" =~ NVIDIA ]]
}

### = is_amd_gpu: - GPU is amd
function is_amd_gpu() {
    [[ "$HARDWARE_GPU" =~ AMD ]]
}

### = is_intel_gpu: - GPU is intel
function is_intel_gpu() {
    [[ "$HARDWARE_GPU" =~ Intel ]]
}

### = is_3d_gpu: - 3D enabled GPU
function is_3d_gpu() {
    [[ "$HARDWARE_3D" == "True" ]]
}

### = is_multiple_gpu: - GPU more than one
function is_multiple_gpus() {
    [[ "$HARDWARE_GPU" =~ \+ ]]
}

## Support functions
### = load_config: Load variables from a configuration file
function load_config() {
    local config_file="$1"
    if [[ -f "$config_file" ]]; then
        # Validate config file before sourcing
        if bash -n "$config_file"; then
            tui_print_message "Loading configuration from: ${config_file}" "$GREEN" "$PREFIX_SUCCESS"
            source "$config_file"
        else
            tui_print_message "Invalid configuration file syntax: $config_file" "$RED" "$PREFIX_FAILURE"
            exit EXIT_CONFIG_ERROR
        fi
    fi
}

### = validate_required_variables: - Validate required variables exist and correct value
validate_required_variables() {
    local required_vars=("DISK_TARGET" "HOST_NAME" "USER_NAME" "LUKS_NAME")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        tui_print_message "Missing required variables: ${missing_vars[*]}" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_CONFIG_ERROR
    fi
}

### = validate_required_values: - Validate required variable values
function validate_required_values() {
    local required_vars=("DISK_TARGET" "HOST_NAME" "USER_NAME")

    # Validate hostname format
    if [[ ! "$HOST_NAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
        tui_print_message "Invalid hostname format: $HOST_NAME" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_CONFIG_ERROR
    fi

    # Validate username
    if [[ ! "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
        tui_print_message "Invalid username format: $USER_NAME" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_CONFIG_ERROR
    fi

    # Validate disk path
    if [[ ! "$DISK_TARGET" =~ ^/dev/[a-zA-Z0-9]+$ ]]; then
        tui_print_message "Invalid disk path: $DISK_TARGET" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_CONFIG_ERROR
    fi
}

### = validate_disk_variables: - Validate disk variables exist and correct value
validate_disk_variables() {
    if [[ ! "$DISK_TARGET" =~ ^/dev/[a-zA-Z0-9]+$ ]]; then
        tui_print_message "Invalid TARGET_DISK format: $DISK_TARGET" "$RED" "$PREFIX_FAILURE"
        exit $EXIT_CONFIG_ERROR
    fi

    # Validate partition naming scheme
    if [[ "$DISK_TARGET" =~ nvme ]]; then
        PART_EFI_PATH="${DISK_TARGET}p1"
        PART_ROOT_PATH="${DISK_TARGET}p2"
        PART_HOME_PATH="${DISK_TARGET}p3"
    else
        PART_EFI_PATH="${DISK_TARGET}1"
        PART_ROOT_PATH="${DISK_TARGET}2"
        PART_HOME_PATH="${DISK_TARGET}3"
    fi
}

### = validate_config: - Validate all variables
validate_config() {
    validate_required_variables
    validate_required_values
    validate_disk_variables
}

### = init_logging: Setup log files
function init_logging() {
    local log_dir="logs/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$log_dir"

    LOG_COMMANDS="$log_dir/commands.log"
    LOG_ERRORS="$log_dir/error.log"

    # Log session start
    {
        echo "=== Arch Linux Installation Started ==="
        echo "Date: $(date)"
        echo "User: $(whoami)"
        echo "Host: $(uname -n)"
        echo "======================================="
    } | tee -a "$LOG_COMMANDS" "$LOG_ERRORS"
}

### = display_help: Show usage information
function display_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c, --config FILE   Specify an alternate configuration file."
    echo "                      (Default: $CONFIG_FILE)"
    echo "  -v, --verbose       Show the actual shell command instead of the description."
    echo "  -d, --dry-run       Do not execute the shell commands"
    echo "  -h, --help          Display this help message."
    echo ""
    exit EXIT_SUCCESS
}

### = package_file_to_array: Create array from package file
function package_file_to_array() {

    local file_path="$1"
    local packages_output=""

    if [ ! -f "$file_path" ]; then
        return 1
    fi

    # 1. grep -v '^#'    : Remove lines starting with '#' (comments)
    # 2. grep -v '^\s*$' : Remove lines that are empty or only contain whitespace
    # 3. awk '{print $1}': Print only the first field (the package name)
    # 4. tr '\n' ' '     : Translate all newlines into single spaces
    # 5. sed 's/ $//'    : Remove the trailing space left by tr

    # The entire process is now done using awk for better parsing and quoting
    packages_output=$(cat "$file_path" | \
        grep -v '^\s*#\|^$' | \
        awk '{print $1}' | \
        while IFS= read -r pkg; do
            # Wrap each package name in quotes
            printf "\"%s\" " "$pkg"
        done)

    # Echo the final quoted string. Example: "base" "base-devel" "linux" ...
    echo "$packages_output" | sed 's/ $//' # Remove trailing space

    return 0
}

### = display_config: Show all config variables
display_config() {
    tui_print_section "Arch Install Configuration" "$YELLOW"

    # --- 1. DISK AND PARTITIONING ---
    tui_print_message "### DISK CONFIGURATION ###" "$YELLOW"
    tui_print_message "Target Disk:       $DISK_TARGET" "$WHITE" "- "
    tui_print_message "Part. EFI Path:    $PART_EFI_PATH" "$WHITE" "- "
    tui_print_message "Part. EFI Size:    $PART_EFI_SIZE" "$WHITE" "- "
    tui_print_message "Part. Root Path:   $PART_ROOT_PATH" "$WHITE" "- "
    tui_print_message "Part. Root Size:   $PART_ROOT_SIZE" "$WHITE" "- "
    tui_print_message "Part. Root FS:     $PART_ROOT_FS" "$WHITE" "- "
    tui_print_message "Part. Home Path:   $PART_HOME_PATH" "$WHITE" "- "
    tui_print_message "Part. Swap Size:   $SWAP_SIZE_MB MB" "$WHITE" "- "
    tui_print_message ""

    # --- 2. SYSTEM LOCALIZATION AND TIME ---
    tui_print_message "### LOCALIZATION ###" "$YELLOW"
    tui_print_message "System Locale:     $FB_LOCALE"  "$WHITE" "- "
    tui_print_message "Timezone:          $FB_TIMEZONE" "$WHITE" "- "
    tui_print_message "Console Keymap:    $FB_KEYMAP" "$WHITE" "- "
    tui_print_message "Console Font:      $FONT" "$WHITE" "- "
    tui_print_message ""

    # --- 3. NETWORK AND HOSTNAME ---
    tui_print_message "### NETWORK & HOST ###" "$YELLOW"
    tui_print_message "Hostname:          $HOST_NAME" "$WHITE" "- "
    tui_print_message ""

    # --- 4. USER AND ROOT ACCOUNTS ---
    tui_print_message "### USERS & SHELL ###" "$YELLOW"
    tui_print_message "Main User:         $USER_NAME" "$WHITE" "- "
    tui_print_message "User Shell:        $USER_SHELL" "$WHITE" "- "
    tui_print_message ""

    # --- 5. PACMAN AND SOFTWARE (Array Handling) ---
    tui_print_message "### SOFTWARE & BOOT ###" "$YELLOW"
    tui_print_message "Bootloader:        $BOOTLOADER" "$WHITE" "- "
    tui_print_message ""

    # --- 6. HARDWARE DETECTED ---
    tui_print_message "### HARDWARE DETECTION ###" "$YELLOW"
    tui_print_message "CPU:              $HARDWARE_CPU" "$WHITE" "- "
    tui_print_message "GPU:              $HARDWARE_GPU" "$WHITE" "- "
    tui_print_message "3D Support:       $HARDWARE_3D" "$WHITE" "- "
    tui_print_message "Virtual:          $HARDWARE_VIRTUAL" "$WHITE" "- "
    tui_print_message ""

    # --- 7. PACKAGES TO INSTALL ---
    PACKAGES_BASE_ARRAY_STRING=$(package_file_to_array "packages/pacman_base")
    PACKAGES_UTILS_ARRAY_STRING=$(package_file_to_array "packages/pacman_utils")
    PACKAGES_HARDWARE_ARRAY_STRING=$(package_file_to_array "PACKAGES_HARDWARE")

    eval "PACKAGES_BASE=($PACKAGES_BASE_ARRAY_STRING)"
    eval "PACKAGES_UTILS=($PACKAGES_UTILS_ARRAY_STRING)"
    eval "PACKAGES_HARDWARE=($PACKAGES_HARDWARE_ARRAY_STRING)"

    tui_print_message "### SOFTWARE PACKAGES ###" "$YELLOW"

    # Safely list Base Packages
    if [ ${#PACKAGES_BASE[@]} -gt 0 ]; then
        tui_print_message "Base Packages:     ${PACKAGES_BASE[*]}" "$WHITE" "- "
    else
        tui_print_message "Base Packages:     (Empty or not defined)" "$WHITE" "- "
    fi

    # Safely list Hardware Packages
    if [[ ${#PACKAGES_HARDWARE[@]} -gt 0 ]]; then
        tui_print_message "Hardware Packages: ${PACKAGES_HARDWARE[*]}" "$WHITE" "- "
    else
        tui_print_message "Hardware Packages: (Empty or not found)" "$WHITE" "- "
    fi

    # Safely list Common Packages
    if [ ${#PACKAGES_UTILS[@]} -gt 0 ]; then
        tui_print_message "Common Packages:   ${PACKAGES_UTILS[*]}" "$WHITE" "- "
    else
        tui_print_message "Common Packages:   (Empty or not defined)" "$WHITE" "- "
    fi

    echo ""
    input_info "Continue with this configuration? [y/N]: "
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        tui_print_message "Installation cancelled by user" "$YELLOW"
        exit 0
    fi
}

### = display_hardware_recommendation: Hardware help
function display_hardware_recommendations() {
    local recommendations=()

    if is_nvidea_gpu && is_intel_gpu; then
        recommendations+=("Consider installing optimus-manager for GPU switching")
        recommendations+=("Install nvidia-prime for NVIDIA Optimus support")
    fi

    if is_nvidea_gpu; then
        recommendations+=("Install NVIDIA drivers: pacman -S nvidia nvidia-utils")
        recommendations+=("Reboot required after NVIDIA driver installation")
    fi

    if is_virtual_machine; then
        case "$HARDWARE_VIRTUAL" in
            "VMware")
                recommendations+=("Install VMware Tools for better integration")
                recommendations+=("Enable shared folders if needed")
                ;;
            "VirtualBox")
                recommendations+=("Install VirtualBox Guest Additions")
                recommendations+=("Enable 3D acceleration in VM settings")
                ;;
            "QEMU/KVM")
                recommendations+=("Install SPICE guest agent for clipboard sharing")
                recommendations+=("Consider using virtio drivers for better performance")
                ;;
        esac
    fi

    if [[ ${#recommendations[@]} -gt 0 ]]; then
        tui_print_title "Recommendations"
        for rec in "${recommendations[@]}"; do
            display_info "  • $rec"
        done
        tui_print_line
    fi
}

### = get_password: Enter password and check
# ==============================================================
# 🔐 Function to securely read and confirm a password
# Arguments:
#   $1 - The type of account (e.g., "User", "LUKS")
#   $2 - The prompt message prefix (e.g., "Enter password")
# Returns: The final, matching plaintext password to stdout
# Exits: With code 0 on success, 1 on failure/mismatch
# ==============================================================
get_password() {
    local account_type="$1"
    local prompt_prefix="$2"
    local pass1=""
    local pass2=""

    while true; do
        # --- First Prompt ---
        # Combines the custom prefix with the account type for the prompt
        input_info "${prompt_prefix} for ${account_type}: "
        read -r -s pass1
        echo >&2

        # --- Second Prompt ---
        input_info "Confirm password for ${account_type}: "
        read -r -s pass2
        echo >&2

        # --- Validation ---
        if [ -z "$pass1" ]; then
            tui_print_message "Password cannot be empty. Please try again." "$YELLOW"
        elif [ "$pass1" != "$pass2" ]; then
            tui_print_message "Passwords do not match. Please try again." "$RED"
        else
            # Return the password by echoing it to stdout
            echo "$pass1"
            return 0 # Success
        fi

        # Only return 1 if the user hits Ctrl+C or a critical error occurs,
        # otherwise the loop handles retries.
    done
    return 1 # Should only be reached if loop is broken unexpectedly
}

### = run: Run a command with status indicators and log outputs (with spinner)
function run() {
    # 1. Function Setup and Variable Declaration
    local command="$1"          # The shell command to run
    local pipe_input="${2:-}"   # The string to be piped into the command (optional)
    local pid
    local status=0
    local full_command
    local display_text
    local sanitized_command

    # 2. Command Construction and Display Setup

    if [ -n "$pipe_input" ]; then
        full_command="printf '%s' \"$pipe_input\" | $command"

        # --- PRIMARY PIPE SANITATION (Used directly if piping is present) ---
        # If there is pipe input, set the display text to the clean version immediately.
        display_text="printf [SECRET] | $command"
    else
        full_command="$command"
        display_text="$command"

        # 3. Security Enhancement & Display (ONLY run if no pipe is used)
        # If no pipe is used, we check the command for secrets passed as arguments.
        sanitized_command=$(
            echo "$display_text" | \
            # Target explicit password flags: -p, --password
            sed -E "s/(-p|--password)[[:space:]]*(\"[^\"]+\"|'[^']+'|[^[:space:]]+)/\1 [SECRET]/g"
        )
        display_text="$sanitized_command"
    fi

    # Create a unique temporary file path for output capture.
    local temp_output
    temp_output=$(mktemp)

    # 4. Log Command to COMMAND_LOG
    echo "$display_text" >> "$LOG_COMMANDS"

    # 5. Display Running Status
    tui_start_spinner "$display_text"

    # 6. Execute Command in Background, when not in dry run
    if [ "$DRYRUN" -eq 0 ]; then
        eval "$full_command" > "$temp_output" 2>&1 &
        pid=$!

        # 7. Wait for Completion
        wait "$pid"
        status=$?
    fi

    # 8. Process Logs (ERROR_LOG)
    echo "--- START: $display_text (Status: $status) ---" >> "$LOG_ERRORS"
    cat "$temp_output" >> "$LOG_ERRORS"

    # 9. Conditional TTY Output (VERBOSE=1)
    if [ "$VERBOSE" -eq 1 ]; then
        tui_stop_spinner "$status" "$display_text"

        if [ -s "$temp_output" ]; then
            echo -e "\n[ Command Output Start ]"
            cat "$temp_output"
            echo -e "[ Command Output End ]\n"
        fi
    fi

    # 10. Check Status and Stop Spinner
    if [ "$status" -eq 0 ]; then
        # Success path
        if [ "$VERBOSE" -eq 0 ]; then
            tui_stop_spinner 0 "$display_text"
        fi
        rm -f "$temp_output"
    else
        # Failure path
        echo "Command FAILED (Exit Code: $status). Error output captured below:" >> "$LOG_COMMANDS"
        cat "$temp_output" >> "$LOG_COMMANDS"

        tui_stop_spinner "$status" "$display_text"

        local error_message="Command failed for: $display_text (Exit Code $status). See $LOG_ERRORS for full output and $LOG_COMMANDS for errors."
        tui_print_message "$error_message" "$RED" "[CRITICAL]"

        rm -f "$temp_output"
        exit "$EXIT_COMMAND_ERROR"
    fi
}

### = run_chroot: Run a command in the target system
function run_chroot() {
    # 1. Function Setup and Variable Declaration
    local command="$1"
    local pipe_input="${2:-}"
    local pid
    local status=0
    local sanitized_command
    local display_text
    local temp_output

    # Sanity check for chroot directory
    if [ -z "${MOUNT_POINT}" ] || [ ! -d "${MOUNT_POINT}" ]; then
        tui_print_message "CHROOT_DIR is not set or not a valid directory. Cannot run arch-chroot." "$RED" "[CRITICAL]"
        exit "$EXIT_CONFIG_ERROR"
    fi

    # 2. Command Construction for Execution
    local full_host_command="arch-chroot ${MOUNT_POINT} sh -c \"$command\""

    if [ -n "$pipe_input" ]; then
        # The full command that will be evaluated
        full_host_command="printf '%s' \"$pipe_input\" | $full_host_command"

        # PRIMARY PIPE SANITATION: Set the display text to the clean version immediately.
        display_text="printf [SECRET] | arch-chroot ${MOUNT_POINT} sh -c \"$command\""
    else
        # If no pipe input, the host command is the display text.
        display_text="$full_host_command"
    fi

    # 3. Security Enhancement & Display Setup (General cleanup for arguments inside sh -c)
    # This catches secrets passed as arguments like -p 'pass'.
    sanitized_command=$(
        echo "$display_text" | \
        sed -E "s/(-p|--password)[[:space:]]*(\"[^\"]+\"|'[^']+'|[^[:space:]]+)/\1 [SECRET]/g"
    )

    # Final display string
    display_text="$sanitized_command"

    # Create a unique temporary file path for output capture.
    temp_output=$(mktemp)

    # 4. Log Command to COMMAND_LOG
    echo "$sanitized_command" >> "$LOG_COMMANDS"

    # 5. Display Running Status
    tui_start_spinner "$display_text"

    # 6. Execute Command in Background, when not in dry run
    if [ "$DRYRUN" -eq 0 ]; then
        eval "$full_host_command" > "$temp_output" 2>&1 &
        pid=$!

        # 7. Wait for Completion
        wait "$pid"
        status=$?
    fi

    # 8. Process Logs (ERROR_LOG)
    echo "--- START: $display_text (Status: $status) ---" >> "$LOG_ERRORS"
    cat "$temp_output" >> "$LOG_ERRORS"

    # 9. Conditional TTY Output (VERBOSE=1)
    if [ "$VERBOSE" -eq 1 ]; then
        tui_stop_spinner "$status" "$display_text"

        if [ -s "$temp_output" ]; then
            echo -e "\n[ Chroot Command Output Start ]"
            cat "$temp_output"
            echo -e "[ Chroot Command Output End ]\n"
        fi
    fi

    # 10. Check Status and Stop Spinner
    if [ "$status" -eq 0 ]; then
        # Success path
        if [ "$VERBOSE" -eq 0 ]; then
            tui_stop_spinner 0 "$display_text"
        fi
        rm -f "$temp_output"
    else
        # Failure path
        echo "Chroot Command FAILED (Exit Code: $status). Error output captured below:" >> "$LOG_COMMANDS"
        cat "$temp_output" >> "$LOG_COMMANDS"

        tui_stop_spinner "$status" "$display_text"

        local error_message="Chroot command failed for: $display_text (Exit Code $status). See $LOG_ERRORS for full output and $LOG_COMMANDS for errors."
        tui_print_message "$error_message" "$RED" "[CRITICAL]"

        rm -f "$temp_output"
        exit "$EXIT_COMMAND_ERROR"
    fi
}

## Setup script logic
### = parse_arguments: Set variables depending on arguments passed
function parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -c|--config)        # Load variables from external config file
                CONFIG_FILE="$2"
                shift 2
                ;;
            -v|--verbose)       # Display shell command outputs
                VERBOSE=1
                shift
                ;;
            --dry-run)          # Do not execute the commands
                DRYRUN=1
                shift
                ;;
            -h|--help)          # Show help options
                display_help
                exit 0
                ;;
            *)
                tui_print_message "Unknown option: $1" "$YELLOW"
                display_help
                ;;
        esac
    done
}


### = get_user_info: Get the passwords for user and LUKS
function get_user_info() {

    tui_print_section "Provide security details"
    USER_PASSWORD=$(get_password "$USER_NAME" "Enter password") || exit 1
    LUKS_PASSWORD=$(get_password "Luks" "Enter password") || exit 1
}

## Device and Partition functions
### = device_reset: - Clear device, partitions, randomise, etc
function device_reset() {

    # Wipe partition table and inform the operating system
    run "wipefs -af $DISK_TARGET"
    run "sgdisk --zap-all --clear $DISK_TARGET"
    run "partprobe ${DISK_TARGET}"

    ### Zero the target drive
    # display_info "Zero the target drive"
    # # When security is important the disk content should contain random data
    # # Plain dm-crypt is used for a very fast wipe with randomness.
    # # Create a temporary crypt device
    # run "cryptsetup open --type plain -d /dev/urandom $TARGET_DISK target"

    # # This maps the container under /dev/mapper/target with a random password.
    # # Fill the container with a stream of zeros using dd
    # run "dd if=/dev/zero of=/dev/mapper/target bs=1M status=progress oflag=direct"

    # # Using if=/dev/urandom is not required as the dm-crypt cipher is used for randomness.
    # # When dd is finished, remove the mapping.
    # run "cryptsetup close target"
}

### = device_partitions_create - Create device partitions
function device_partitions_create() {

    # The layout is for a single SSD with a GPT partition table that contains two partitions:
    # - Partition 1 - EFI boot partition (ESP) - size 1024MiB, code ef00
    # - Partition 2 - CRYPTROOT Encrypted partition (LUKS) - remaining storage, code 8304
    # - Partition 3 - HOME Home partition - remaining storage, code 8302
    # - Note - the Discoverable Partition Specifications mentions 8304 for root
    # - Note - we are setting the GPT Partition name (not the file system label)
    #          Use sgdisk p /dev/sdx to show
    run "sgdisk -n 1:0:+1024MiB -t 1:ef00 -c 1:EFI       ${DISK_TARGET}"
    run "sgdisk -n 2:0:+10GiB   -t 2:8304 -c 2:CRYPTROOT ${DISK_TARGET}"
    run "sgdisk -n 3:0:0        -t 3:8302 -c 3:HOME      ${DISK_TARGET}"

    # Inform the OS of the new parititons
    run "partprobe ${DISK_TARGET}"
}

### = device_encrypt_root - Encrypt root partition
function device_encrypt_root() {

    # Encrypt root partition with LUKS 2
    # When systemd runs in the initial RAM disk (initrd) and detects a root partition
    # with a recognized architecture-specific root GPT GUID that is LUKS-encrypted,
    # it will open the volume with the name root, creating the device node at /dev/mapper/root
    run "cryptsetup luksFormat /dev/disk/by-partlabel/CRYPTROOT" "${LUKS_PASSWORD}"
    run "cryptsetup open /dev/disk/by-partlabel/CRYPTROOT root" "${LUKS_PASSWORD}"
}

### = device_partitions_format
function device_partitions_format() {
    # Format the EFI partition with vfat
    run "mkfs.fat -F 32 -n ESP /dev/disk/by-partlabel/EFI"

    # Format the encrypted root partition with BTRFS
    run "mkfs.btrfs -f -L Root /dev/mapper/root"

    # Format the Home partition. Left unencrypted as systemd-homed does that again.
    run "mkfs.btrfs -f -L Home /dev/disk/by-partlabel/HOME"
}

### = device_btrfs_subvolumes_create - Create BTRFS sub volumes
function device_btrfs_subvolumes_create() {

    # Mount the root partition:
    run "mount /dev/mapper/$LUKS_NAME ${MOUNT_POINT}"

    # Each BTRFS filesystem has a top-level subvolume with ID=5. A subvolume is a part of the filesystem with its own independent data.
    # Creating subvolumes on a BTRFS filesystem allows the separation of data. This is particularly useful when creating backup snapshots of the system. An example scenario might be where its desirable to rollback a system after a broken upgrade, but any changes made in a user's /home directory should be left alone.
    # Changing subvolume layouts is made simpler by not mounting the top-level subvolume as / (the default). Instead, create a subvolume that contains the actual data, and mount that to /.
    # Use @ for the name of this new subvolume (which is the default for Snapper, a tool for making backup snapshots)
    run "btrfs subvolume create ${MOUNT_POINT}/@"

    # Create additional subvolumes for more fine-grained control over rolling back the system to a previous state, while preserving the current state of other directories. These subvolumes will be excluded from any root subvolume snapshots:
    # Subvolume -- Mountpoint
    # - @snapshots -- /.snapshots
    # - @cache -- /var/cache
    # - @libvirt -- /var/lib/libvirt (virtual machine images)
    # - @log -- /var/log (excluding log files makes troubleshooting easier after reverting /)
    # - @tmp -- /var/tmp
    # The reasoning behind not excluding the entire /var out of the root snapshot is that /var/lib/pacman database in particular should mirror the rolled back state of installed packages.
    run "btrfs subvolume create ${MOUNT_POINT}/@cache"
    run "btrfs subvolume create ${MOUNT_POINT}/@log"
    run "btrfs subvolume create ${MOUNT_POINT}/@tmp"
    run "btrfs subvolume create ${MOUNT_POINT}/@snapshots"
    run "btrfs subvolume create ${MOUNT_POINT}/@libvirt"
    run "btrfs subvolume create ${MOUNT_POINT}/@docker"

    # Unmount the root partition
    run "umount ${MOUNT_POINT}"
}

### = device_btrfs_subvolumes_mount: - Mount BTRFS sub volumes
function device_btrfs_subvolumes_mount {

    # Note the -t btrfs is to specify the filesystem type and help shell completion. The subvol option specifies which subvolume to mount.
    # Also note that the mount '-m' command creates the mount point if it does not already exist (${MOUNT_POINT}/home, etc )
    # Compression is enabled with zstd, which saves space and can improve performance. The zstd:1 means compression level 1 (range 1-5, default 3).
    # According to Arch Wiki, level 1 improves fragmentation and reduces IO, potentially improving performance.
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@ -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@cache -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/cache"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@log -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/log"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@tmp -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/tmp"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@snapshots -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/.snapshots"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@libvirt -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/libvirt"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@docker -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/docker"

    # Note that disabling CoW will simultaneously disable Btrfs snapshotting, data checksumming, and compression.
    # This is mainly to avoid frequent writes on directories like log, cache, tmp, and var/tmp which generally do not need snapshots.
    # Also, docker, podman, and libvirt use their own image formats, and using CoW may cause performance issues.
    run "chattr +C ${MOUNT_POINT}/var/lib/libvirt"
    run "chattr +C ${MOUNT_POINT}/var/lib/docker"

    # Mount EFI partition:
    run "mount --mkdir LABEL=ESP ${MOUNT_POINT}/efi"

    # Mount HOME partition
    run "mount --mkdir LABEL=Home ${MOUNT_POINT}/home -o compress-force=zstd,noatime"
}

### = device_partitions_mount: - Helper function to mount existing install
function device_partitions_mount() {

    # Open the root partiton (LUKS)
    run "cryptsetup open /dev/disk/by-partlabel/CRYPTROOT root" "$LUKS_PASSWORD"

    # Mount ROOT and root sub-volumes
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@ -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@cache -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/cache"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@log -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/log"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@tmp -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/tmp"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@snapshots -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/.snapshots"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@libvirt -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/libvirt"
    run "mount -t btrfs -o ${PART_ROOT_FS_BTRFS_OPTIONS},subvol=@docker -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/docker"

    # Mount ESP
    run "mount --mkdir LABEL=ESP ${MOUNT_POINT}/efi"

    # Mount HOME
    run "mount --mkdir LABEL=Home ${MOUNT_POINT}/home -o compress-force=zstd,noatime"
}

## Linux Installation functions
### = install_disk: Configure disks and partitions
function install_disk() {
    ### Install Disk Configuration
    tui_print_title "Install Disk Configuration"

    device_reset
    device_partitions_create
    device_encrypt_root
    device_partitions_format
    device_btrfs_subvolumes_create
    device_btrfs_subvolumes_mount
}

### = install_linux_base: Pacstrap Arch Linux base (minimal)
install_linux_base() {
    ### Install Linux OS packages
    tui_print_title "Install Arch Linux - base"

    ### Reflector
    # Before installation, use the reflector command to update mirror lists. Replace --country with your country or a nearby one.
    run "reflector --country ${FB_COUNTRY} --latest 10 --age 24 --protocol http,https --sort rate --save /etc/pacman.d/mirrorlist"

    ### Pacman Configuration
    # Arch Linux from October 2024 have 5 parallel downloads enabled by default.

    # Load the packages from the /packages/pacman_base file
    # base            # ✅     Base system packages
    # base-devel      # ✅     Base development tools
    # linux           # ✅     Linux kernel
    # linux-firmware  # ✅     Linux firmware
    # btrfs-progs     # ✅     Btrfs support
    # util-linux      # ✅     Linux utilities, essential for system operation
    # cryptsetup      # ✅     Encryption/decryption tools used later
    # dosfstools      # ✅     FAT filesystem tools (e.g., mkfs.fat)
    # sbctl           # ✅     Secure Boot tool used later
    # mg              # ✅     Text editor (install at least one of your choice)
    # networkmanager  # ✅     Network manager; recommended for desktop environments
    # sudo            # ✅     Privilege escalation tool; essential to avoid system reinstall
    # git             # ✅     Git version control, frequently used

    run "grep -o '^[^ *#]*' packages/pacman_base > LINUX_BASE"

    # Add detected hardware packages (from file) to the Linux Base packages file
    if [[ -f PACKAGES_HARDWARE ]]; then
        run "grep -v '^#' PACKAGES_HARDWARE | grep -v '^$' >> LINUX_BASE"
    fi

    # Pacstrap Linux OS packages
    run "pacstrap -K ${MOUNT_POINT} - < LINUX_BASE"

    # Generate the fstab file that contains all mount points
    # run "genfstab -U ${MOUNT_POINT} >> ${MOUNT_POINT}/etc/fstab"
    # Use partition UUID for source identification
    run "genfstab -t PARTUUID ${MOUNT_POINT} >> ${MOUNT_POINT}/etc/fstab"

    # Clean up the created files
    run "rm -f PACKAGES_HARDWARE LINUX_BASE"
}

### = install_firstboot: Configure Arch linux to user locations
function install_firstboot() {

    # Set the language characters
    # Note when debugging the file might not exist

    if [[ -f "${MOUNT_POINT}/etc/locale.gen" ]]; then
        run "sed -i -e "/^#${FB_LOCALE}/s/^#//" ${MOUNT_POINT}/etc/locale.gen"
    fi

    # Using a local FIRSTBOOT file with the parameters
    # systemd-firstboot Options for Non-Interactive Setup (Version 258.1)
    #
    # Option ( Flag)                  Required Description
    # -----------------------------   -------- ----------------------------------------------------
    # --root=/path                    ✅       Target system's root directory (e.g., /mnt).
    # --locale=LOCALE                 ✅       Sets the system locale (e.g., en_US.UTF-8).
    # --keymap=KEYMAP                 ✅       Sets the console keymap (e.g., us).
    # --timezone=ZONE                 ✅       Sets the system time zone (e.g., Australia/Melbourne).
    # --hostname=NAME                 ✅       Sets the system hostname (e.g., my-arch-box).
    # --root-password-hash            ❌       Sets the root password using a pre-generated hash.
    # --machine-id=ID                 ❌       Sets the 128-bit hexadecimal machine ID.
    # --setup-mode=MODE               ❌       Configures system as a container, host, or appliance.
    # --image=PATH                    ❌       Sets the operating system image version identifier.
    # --kernel-version=VERSION        ❌       Sets the operating system kernel version identifier.
    # --json=pretty                   ❌       Prints status information in JSON format.
    # --no-pager                      ❌       Disables piping output into a pager.
    #
    # NOTE: The flags --prompt-all=no and --no-prompt are not valid options
    #       in modern systemd versions. Non-interactive behavior is triggered
    #       simply by providing values for all required settings (the '✅' items).

    # Configure Locale
    run "echo -n '--root=${MOUNT_POINT} ' > FIRSTBOOT"
    run "echo -n '--locale=${FB_LOCALE} ' >> FIRSTBOOT"
    run "echo -n '--keymap=${FB_KEYMAP} ' >> FIRSTBOOT"
    run "echo -n '--timezone=${FB_TIMEZONE} ' >> FIRSTBOOT"
    run "echo -n '--hostname=${HOST_NAME} ' >> FIRSTBOOT"
    run "echo -n '--root-password-hashed=${ROOT_PASS_HASHED} ' >> FIRSTBOOT"

    # Setup the new Arch Linux system
    # Pass the arguments to systemd-firstboot as piping does not work
    run "xargs -a FIRSTBOOT systemd-firstboot"

    # Cleanup
    if [ -z "${DEBUG}" ]; then
        run "rm FIRSTBOOT"
    fi

    # Generate the local file
    run_chroot "locale-gen"
}

### = install_user: Configure main user
function install_user() {

    # Add user account, set users password and default shell
    run_chroot "useradd -G wheel -s ${USER_SHELL} -m ${USER_NAME}"
    run_chroot "chpasswd" "${USER_NAME}:${USER_PASSWORD}"

    # Allow the WHEEL group to run sudo commands, without providing password
    run "cp -f rootfs/etc/sudoers ${MOUNT_POINT}/etc/sudoers"
}

### = install_uki: Configure Universal Kernel Images
function install_uki() {

    # Create the folder for the kernel images
    run "mkdir -p ${MOUNT_POINT}/efi/EFI/Linux"

    # Set the kernel commands line
    run "echo -n 'quiet rw' > ${MOUNT_POINT}/etc/kernel/cmdline"

    # Because we are using sub volumes, to root has changed from default / to @
    # Tell that the root is the @ btrfs sub-volume
    run "echo -n ' rootflags=subvol=@' >> ${MOUNT_POINT}/etc/kernel/cmdline"

    # Copy the kernel configuration
    run "cp -f rootfs/etc/mkinitcpio.d/linux.preset ${MOUNT_POINT}/etc/mkinitcpio.d/linux.preset"

    # Copy the mkinitcpio configuration (HOOKS updated)
    run "cp -f rootfs/etc/mkinitcpio.conf ${MOUNT_POINT}/etc/mkinitcpio.conf"

    # Generate kernel images
    run_chroot "mkinitcpio -P"
}

### = install_services: Configure services
function install_services() {

    # Enable services
    run "systemctl --root ${MOUNT_POINT} enable systemd-resolved systemd-timesyncd NetworkManager"

    # Make services
    run "systemctl --root $MOUNT_POINT mask systemd-networkd"

    # Install systemd-boot services to /efi
    # /usr/lib/systemd/boot/efi/systemd-bootx64.efi will be copied to
    # - esp/EFI/systemd/systemd-bootx64.efi and
    # - esp/EFI/BOOT/BOOTX64.EFI
    # systemd-boot will try to locate the ESP at /efi, /boot, and /boot/efi
    # To create the boot entry in the chroot environment, use arch-chroot -S
    run_chroot "bootctl install"
}

### = install_review
function install_review() {
    # -----------------------------------------------------------
    # Define files to review (relative to the mounted root /mnt)
    # -----------------------------------------------------------
    local INSTALL_FILES=(
        # systemd-firstboot configuration outputs
        "/etc/hostname"
        "/etc/vconsole.conf"
        "/etc/locale.conf"
        "/etc/sudors"

        # UKI/Boot Loader configurations (assuming common setup paths)
        "/etc/fstab"                              # Mount points
        "/etc/kernel/cmdline"                     # Kernel command line
        "/etc/mkinitcpio.conf"
        "/etc/mkinitcpio.d/linux.preset"
    )

    local INSTALL_DIRS=(
        # EFI/Boot directories (must exist relative to mounted root /mnt)
        "/efi/EFI/Linux"       # Check UKI placements
        "/efi/EFI/systemd"     # Check for systemd-boot systemd-bootx64.efi
        "/efi/EFI/BOOT"        # Check for systemd-boot BOOTX64.EFI
        "/efi/loader/entries"  # Check for systemd-boot boot entries
        "/boot"                # Check for initfram and ucode
    )

    tui_print_title "Installation Review"
    tui_print_message "Configuration files and folders were created or modified."
    tui_print_message "You may want to review their content before rebooting."
    tui_print_line "$YELLOW"

    read -r -p "Do you want to **review** the installation?  [Y/N] " initial_choice

    case "$initial_choice" in
        [nN])
            tui_print_message "Skipping all reviews"
            return # Exit the function immediately
            ;;
        [yY]*|"")
            # Continue with the individual prompts
            ;;
        *)
            tui_print_message "Invalid choice. Skipping all reviews"
            return # Exit the function immediately
            ;;
    esac

    # Iterate through the list of files
    for FILE in "${INSTALL_FILES[@]}"; do
        local FULL_PATH="${MOUNT_POINT}${FILE}"

        # Check if the file actually exists before asking to view it
        if [ -f "$FULL_PATH" ]; then

            # Simple prompt logic
            read -r -p "Review content of ${FILE}? [Y/n] " choice

            case "$choice" in
                [yY]*|"")
                    echo ""
                    tui_print_title "Content of ${FILE}"
                    # Use 'cat' for simple output, or 'less' for long files
                    # cat "$FULL_PATH"
                    more "$FULL_PATH"
                    tui_print_line "End of ${FILE}"
                    ;;
                [nN]*)
                    continue # Skip to the next file
                    ;;
                *)
                    tui_print_message "Invalid choice. Skipping." "$YELLOW"
                    ;;
            esac
        else
            tui_print_message "File ${FILE} does not exist. Skipping." "$YELLOW" "$PREFIX_WARNING"
        fi
    done

    for DIR in "${INSTALL_DIRS[@]}"; do
        local FULL_PATH="${MOUNT_POINT}${DIR}"

        if [ -d "$FULL_PATH" ]; then
            read -r -p "List contents of ${DIR}? [Y/n] " choice

            case "$choice" in
                [yY]*|"")
                    tui_print_title "Listing contents of ${DIR}"
                    # Use ls -lah for human-readable sizes and full details
                    ls -lah "$FULL_PATH"
                    tui_print_line "End of ${DIR} Listing"
                    ;;
                [nN]*)
                    continue
                    ;;
                *)
                    tui_print_message "Invalid choice. Skipping." "$YELLOW"
                    ;;
            esac
        else
            tui_print_message "Directory ${DIR} does not exist. Skipping." "$YELLOW" "$PREFIX_WARNING"
        fi
    done

    tui_print_title "Review Complete"
}

## Main
main() {

    # Setup system and configuration
    clear
    init_logging
    detect_hardware
    parse_arguments "$@"
    load_config "$CONFIG_FILE"
    validate_config
    display_config

    # Check host and tarfet system
    clear
    preflight_checks

    # Main installation logic would go here
    get_user_info

    clear
    install_disk
    install_linux_base
    install_firstboot
    install_user
    install_uki
    install_services
    install_review

    # cleanup_all
}

# Only run main if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
