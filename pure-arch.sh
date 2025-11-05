#!/bin/bash
set -e                          # Exit on error

# Define colors
YELLOW="\033[1;33m"             # Yellow
GREEN="\033[1;32m"              # Green
RED="\033[1;31m"                # Red
CYAN="\033[1;36m"               # Cyan
MAGENTA="\033[1;35m"            # Magenta
BOLD_YELLOW='\033[1;33m'        # Bold Yellow
RESET="\033[0m"                 # Reset color

# Default Configuration File
CONFIG_FILE="config.conf"

# Log files
COMMAND_LOG="logs/commands.log"  # Log file for commands executed
FEEDBACK_LOG="logs/feedback.log" # Log file for feedback (RUNNING, COMPLETED, FAILED)
ERROR_LOG="logs/error.log"       # Log file for errors

# Global Variables
DEBUG=0                         # 1=Debug is active
VERBOSE=0                       # 1=Show shell execution output
DRYRUN=0                        # 1=Do net execute to shell commands
MOUNT_POINT=/mnt                # Mount point for Arch Linux installation

# Hardware Detection Global Variables
HARDWARE_CPU=""          # Intel, AMD, Unknown
HARDWARE_GPU=""          # Intel, AMD, NVIDIA, Basic, None, Intel+NVIDIA, AMD+NVIDIA, etc.
HARDWARE_3D=""           # True, False, Limited
HARDWARE_VIRTUAL=""      # None, VMware, VirtualBox, QEMU/KVM, Hyper-V, Xen, Parallels
HARDWARE_DISPLAY=""      # Full display string: "CPU: Intel | GPU: NVIDIA | 3D: True | Virtual: None"

# Fixed variables
readonly LUKS_NAME="root"       # 'root' is required by the Discoverable Partitions Specifications

# Default Configuration Variables
TARGET_DISK="/dev/sdb"
EFI_PARTITION="${TARGET_DISK}1"
ROOT_PARTITION="${TARGET_DISK}2"
SWAP_PARTITION="${TARGET_DISK}3"
ROOT_FS_TYPE="btrfs"
BTRFS_OPTIONS="rw,noatime,compress-force=zstd:1,space_cache=v2"
SWAP_SIZE_MB="8192"
SYSTEM_LOCALE="en_US.UTF-8"
SYSTEM_COUNTRY="Australia"
TIME_ZONE="Australia/Victoria"
KEYMAP="us"
FONT="ter-v16b"
HOST_NAME="archlinux"
USER_NAME="echjansen"
USER_PASSWORD="123"
USER_PASS_HASHED="$6$S9DTo9nAHrAYoXqc$Gsg7qyq1jp3Tn2D5ioSjdyr.7hQsvvEgXsAhNiucMv0J574rMUMC5HXoIBc.rJGmbpJiz2U8oIW5JA5Ii/RP41"
LUKS_PASSWORD="123"
ROOT_PASS_HASHED="$6$Cq3RVYFmfLwFSTVs$RPt0RGX6839RH1bxNzfBdkxWai..C8IqqQBH0y3ajcIex3IqtMrKtrp6/NiiQueUpTUcvfJUNNQ1V0TOWP1X21"
USER_SHELL="/bin/bash"
BOOTLOADER="systemd-boot"
BASE_PACKAGES=("base" "linux" "linux-firmware")
COMMON_PACKAGES=("sudo" "git" "mg" "intel-ucode")

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
trap cleanup_all ERR EXIT

### = cleanup: Cleanup potential creations
function cleanup() {

    # Cleanup operations
    run "umount --lazy /dev/mapper/${LUKS_NAME}"
    run "cryptsetup luksClose -q ${LUKS_NAME}"
    run "umount -R -q ${MOUNT_POINT}"

    # Cleanup logs
    run "rm -rf logs/"
}

### = cleanup_all: Close encrypted partitions, umount, etc
function cleanup_all() {
    local exit_code=$?

    # Only run cleanup if there was an actual error
    if [[ $exit_code -ne 0 ]]; then
        display_warning "Installation failed with exit code $exit_code. Cleaning up..."


        display_critical "Installation aborted. Check logs for details."
    fi
}

## TUI Functions
### = display_info: display general information messages in cyan
function display_info() {
    echo -e "${CYAN}$1${RESET}"
}

### = display_section: display section
function display_section() {
    echo ""
    echo -e "${BOLD_YELLOW}========================================${RESET}"
    echo -e "${BOLD_YELLOW} $1${RESET}"
    echo -e "${BOLD_YELLOW}========================================${RESET}"
}

### = display_line: display non-formatted line
function display_line() {
    echo -e "$1"
}

### = display_padded: display == argument =====
function display_padded() {
    local TEXT="$1"
    local TEXT_LENGTH=${#TEXT}
    local MAX_WIDTH=80
    local PADDING_CHAR="="

    # Calculate padding needed on each side
    # We subtract 4 for the "== " prefix and " ==" suffix
    local PADDING_NEEDED=$(( MAX_WIDTH - TEXT_LENGTH - 4 ))

    # Calculate left padding (integer division)
    local LEFT_PADDING=$(( PADDING_NEEDED / 2 ))

    # Calculate right padding (adjust for odd length difference)
    local RIGHT_PADDING=$(( PADDING_NEEDED - LEFT_PADDING ))

    # --- Construct the Output String ---

    # 1. Print the left padding (repeated character string)
    local LEFT_PAD_STRING
    LEFT_PAD_STRING=$(printf '%*s' "$LEFT_PADDING" | tr ' ' "$PADDING_CHAR")

    # 2. Print the right padding (repeated character string)
    local RIGHT_PAD_STRING
    RIGHT_PAD_STRING=$(printf '%*s' "$RIGHT_PADDING" | tr ' ' "$PADDING_CHAR")

    # --- Print the final, 80-character line ---
    # Format: ==[LEFT PADDING][TEXT][RIGHT PADDING]==
    echo -e "${BOLD_YELLOW}==${LEFT_PAD_STRING} ${TEXT} ${RIGHT_PAD_STRING}==${RESET}"
}

### = display_warning: display non-critical warnings in magenta
function display_warning() {
    echo -e "${MAGENTA}[WARNING]${RESET} $1"
}

### = display_success: display successful completion messages in green
function display_success() {
    echo -e "${GREEN}[SUCCESS]${RESET} $1"
}

### = display_critical: display critical errors and failures in red
function display_critical() {
    echo -e "${RED}[CRITICAL]${RESET} $1"
}

### = display_running: display the current step with [RUNNING] in yellow
# This function is now dynamic, using either $description or $command based on $VERBOSE
function display_running() {
    local message="$1"
    echo -n -e "${YELLOW}[-]${RESET} $message"
    tput cub 100 # Move cursor back to the start of the line (to overwrite it)
}

### = display_completed: - mark a step as completed with [COMPLETED] in green
function display_completed() {
    local message="$1"
    # Variables are quoted when used
    echo -e "\r${GREEN}[O]${RESET} $message"  # Overwrite the current line
    echo -e "[COMPLETED] $message" >> "$FEEDBACK_LOG" # Log feedback
}

### = display_failed: mark a step as failed with [FAILED] in red
function display_failed() {
    local message="$1"
    # Variables are quoted when used
    echo -e "\r${RED}[X]${RESET} $message" # Overwrite the current line
    echo -e "[FAILED] $message" >> "$FEEDBACK_LOG" # Log feedback
}

### = input_info: display messages prompting for input in bold yellow
function input_info() {
    # The message is printed using '-n -e' to allow escape codes
    # and to keep the cursor on the same line (no automatic newline).
    echo -n -e "${BOLD_YELLOW}[INPUT]${RESET} $1" >&2
}

## Check functions
# Here is a collection of checks that validate if the target system is suitable for installation.

### = check_root_priviledges: Check if running as root
function check_root_privileges() {
    if [[ $EUID -ne 0 ]]; then
        display_critical "This script must be run as root for Arch installation"
        display_info "Please run: sudo $0"
        exit $EXIT_PERMISSION_ERROR
    fi
    display_success "Running with root privileges"
}

### = check_arch_iso: Check if booted from Arch ISO
function check_arch_iso() {
    if [[ ! -f /etc/arch-release ]]; then
        display_critical "Not running on Arch Linux"
        exit $EXIT_SYSTEM_ERROR
    fi

    # Check if running from live environment
    if ! grep -q "archiso" /proc/cmdline 2>/dev/null; then
        display_warning "Not running from Arch ISO - proceeding anyway"
    else
        display_success "Running from Arch ISO live environment"
    fi
}

### = check_ufi_mode: Check if running in UEFI mode
function check_uefi_mode() {
    if [[ -d /sys/firmware/efi/efivars ]]; then
        display_success "System booted in UEFI mode"
        # Verify EFI variables are writable
        if [[ ! -w /sys/firmware/efi/efivars ]]; then
            display_warning "EFI variables directory is not writable"
        fi
    else
        display_critical "System not booted in UEFI mode"
        display_info "This installer requires UEFI boot mode"
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
            display_success "Internet connectivity verified via $url"
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

    if [[ ! -b "$TARGET_DISK" ]]; then
        display_warning "Target disk $TARGET_DISK not found - skipping disk space check"
        return 0
    fi

    # Get disk size in GB
    local disk_size_bytes
    disk_size_bytes=$(lsblk -b -d -n -o SIZE "$TARGET_DISK" 2>/dev/null)

    if [[ -z "$disk_size_bytes" ]]; then
        display_warning "Could not determine disk size for $TARGET_DISK"
        return 0
    fi

    local disk_size_gb=$((disk_size_bytes / 1024 / 1024 / 1024))

    if [[ $disk_size_gb -lt $required_space_gb ]]; then
        display_critical "Insufficient disk space: ${disk_size_gb}GB available, ${required_space_gb}GB required"
        exit $EXIT_DISK_ERROR
    fi

    display_success "Sufficient disk space available: ${disk_size_gb}GB"
}

### = check_target_disk: Check target disk exists and is accessible
function check_target_disk() {
    if [[ ! -b "$TARGET_DISK" ]]; then
        display_critical "Target disk $TARGET_DISK does not exist or is not a block device"
        display_info "Available disks:"
        lsblk -d -o NAME,SIZE,TYPE | grep disk
        exit $EXIT_DISK_ERROR
    fi

    # Check if disk is writable
    if [[ ! -w "$TARGET_DISK" ]]; then
        display_critical "Target disk $TARGET_DISK is not writable"
        exit $EXIT_DISK_ERROR
    fi

    # Warn if disk contains existing partitions
    if lsblk -n "$TARGET_DISK" | grep -q part; then
        display_warning "Target disk $TARGET_DISK contains existing partitions"
        display_info "Existing partition layout:"
        lsblk "$TARGET_DISK"

        if [[ "$DRYRUN" -eq 0 ]]; then
            input_info "Continue and DESTROY all data on $TARGET_DISK? [y/N]: "
            read -r confirm
            if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                display_info "Installation cancelled by user"
                exit EXIT_SUCCESS
            fi
        fi
    fi

    display_success "Target disk $TARGET_DISK validated"
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
    case "$ROOT_FS_TYPE" in
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
        display_critical "Missing required tools: ${missing_tools[*]}"
        display_info "Please install missing tools or boot from a complete Arch ISO"
        exit $EXIT_DEPENDENCY_ERROR
    fi

    display_success "All required tools are available"
}

### = check_system_clock: Check system clock synchronization
function check_system_clock() {

    # Enable NTP synchronization
    if ! timedatectl set-ntp true 2>/dev/null; then
        display_warning "Could not enable NTP synchronization"
    fi

    # Wait a moment for sync attempt
    sleep 2

    # Check if time is synchronized
    if timedatectl status | grep -q "System clock synchronized: yes"; then
        display_success "System clock is synchronized"
    else
        display_warning "System clock may not be synchronized"
        display_info "Current time: $(date)"
        display_info "This may cause issues with package signatures"
    fi

    # Verify timezone setting
    TIME_ZONE=$(timedatectl show -p Timezone --value)
    display_success "Current timezone: ${TIME_ZONE}"
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
        display_warning "Using total memory for check: ${available_mem_mb}MB"
    fi

    if [[ $available_mem_mb -lt $required_mem_mb ]]; then
        display_warning "Low memory: ${available_mem_mb}MB available, ${required_mem_mb}MB recommended"
        display_info "Installation may be slow or fail with insufficient memory"
    else
        display_success "Sufficient memory available: ${available_mem_mb}MB"
    fi
}

### = check_disk_mounted: Check if target disk is currently mounted (safety check)
function check_disk_mounted() {
    local mounted_partitions
    mounted_partitions=$(lsblk -n -o MOUNTPOINT "$TARGET_DISK" 2>/dev/null | grep -v '^$' || true)

    if [[ -n "$mounted_partitions" ]]; then
        display_warning "Target disk $TARGET_DISK has mounted partitions:"
        lsblk "$TARGET_DISK" | grep -E "(MOUNTPOINT|/)"

        if [[ "$DRYRUN" -eq 0 ]]; then
            display_info "These will be unmounted during installation"
        fi
    else
        display_success "Target disk $TARGET_DISK is not currently mounted"
    fi
}

### = check_all: Perform all checks
function preflight_checks() {
    display_section "Running pre-flight checks..."

    # Check if running as root (required for installation)
    check_root_privileges

    # Check if booted from Arch ISO
    check_arch_iso

    # Check if running in UEFI mode
    check_uefi_mode

    # Check internet connectivity
    # TODO - uncheck
    #check_internet_connectivity

    # Verify disk space requirements
    check_disk_space

    # Validate target disk exists and is accessible
    check_target_disk

    # Validate all required tools are available
    check_required_tools

    # Check system clock synchronization
    check_system_clock

    # Verify memory requirements
    check_memory

    # Check if target disk is mounted (safety check)
    check_disk_mounted

    display_success "All pre-flight checks passed successfully"
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
        echo "# $display_line"
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

    # if [[ ${#packages_hardware[@]} -gt 0 ]]; then
    #     display_info "Hardware packages: ${packages_hardware[*]}"
    # else
    #     display_info "No additional hardware packages needed"
    # fi

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
### = show_spinner: Spinner function with [RUNNING] in yellow
show_spinner() {
    local pid="$1"
    local display_text="$2"
    local delay=0.1
    local spinstr='|/-\'

    while kill -0 "$pid" 2>/dev/null; do  # Better process checking
        for i in $(seq 0 3); do
            # printf "\r${YELLOW}[RUNNING]${RESET} ${spinstr:i:1} $display_text"
            printf "\r${YELLOW}[${spinstr:i:1}]${RESET} $display_text"
            sleep "$delay"
            kill -0 "$pid" 2>/dev/null || break 2
        done
    done
    printf "\r"  # Clear the spinner line
}

### = load_config: Load variables from a configuration file
function load_config() {
    local config_file="$1"
    if [[ -f "$config_file" ]]; then
        # Validate config file before sourcing
        if bash -n "$config_file"; then
            display_info "Loading configuration from: ${config_file}"
            source "$config_file"
        else
            display_critical "Invalid configuration file syntax: $config_file"
            exit EXIT_CONFIG_ERROR
        fi
    fi

    # Validate required variables
    validate_config
}

### = validate_required_variables: - Validate required variables exist and correct value
validate_required_variables() {
    local required_vars=("TARGET_DISK" "HOST_NAME" "USER_NAME" "LUKS_NAME" "ROOT_FS_TYPE")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        display_critical "Missing required variables: ${missing_vars[*]}"
        exit $EXIT_CONFIG_ERROR
    fi
}

### = validate_required_values: - Validate required variable values
function validate_required_values() {
    local required_vars=("TARGET_DISK" "HOST_NAME" "USER_NAME")

    # Validate hostname format
    if [[ ! "$HOST_NAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
        display_critical "Invalid hostname format: $HOST_NAME"
        exit $EXIT_CONFIG_ERROR
    fi

    # Validate username
    if [[ ! "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
        display_critical "Invalid username format: $USER_NAME"
        exit $EXIT_CONFIG_ERROR
    fi

    # Validate disk path
    if [[ ! "$TARGET_DISK" =~ ^/dev/[a-zA-Z0-9]+$ ]]; then
        display_critical "Invalid disk path: $TARGET_DISK"
        exit $EXIT_CONFIG_ERROR
    fi
}

### = validate_disk_variables: - Validate disk variables exist and correct value
validate_disk_variables() {
    if [[ ! "$TARGET_DISK" =~ ^/dev/[a-zA-Z0-9]+$ ]]; then
        display_critical "Invalid TARGET_DISK format: $TARGET_DISK"
        exit $EXIT_CONFIG_ERROR
    fi

    # Validate partition naming scheme
    if [[ "$TARGET_DISK" =~ nvme ]]; then
        EFI_PARTITION="${TARGET_DISK}p1"
        ROOT_PARTITION="${TARGET_DISK}p2"
    else
        EFI_PARTITION="${TARGET_DISK}1"
        ROOT_PARTITION="${TARGET_DISK}2"
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

    COMMAND_LOG="$log_dir/commands.log"
    FEEDBACK_LOG="$log_dir/feedback.log"
    ERROR_LOG="$log_dir/error.log"

    # Log session start
    {
        echo "=== Arch Linux Installation Started ==="
        echo "Date: $(date)"
        echo "User: $(whoami)"
        echo "Host: $(uname -n)"
    } | tee -a "$COMMAND_LOG" "$FEEDBACK_LOG" "$ERROR_LOG"
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

### = display_config: Show all config variables
display_config() {
    display_section "✅ Arch Install Configuration"

    # --- 1. DISK AND PARTITIONING ---
    display_line "### 💾 DISK CONFIGURATION ###"
    display_line "  Target Disk:       $TARGET_DISK"
    display_line "  EFI Partition:     $EFI_PARTITION"
    display_line "  SWAP Partition:    $SWAP_PARTITION"
    display_line "  ROOT Partition:    $ROOT_PARTITION"
    display_line "  Root Filesystem:   $ROOT_FS_TYPE"
    display_line "  SWAP Size:         $SWAP_SIZE_MB MB"
    display_line ""

    # --- 2. SYSTEM LOCALIZATION AND TIME ---
    display_line "### 🌎 LOCALIZATION ###"
    display_line "  System Locale:     $SYSTEM_LOCALE"
    display_line "  Timezone:          $TIME_ZONE"
    display_line "  Console Keymap:    $KEYMAP"
    display_line "  Console Font:      $FONT"
    display_line ""

    # --- 3. NETWORK AND HOSTNAME ---
    display_line "### 🌐 NETWORK & HOST ###"
    display_line "  Hostname:          $HOST_NAME"
    display_line ""

    # --- 4. USER AND ROOT ACCOUNTS ---
    display_line "### 👤 USERS & SHELL ###"
    display_line "  Main User:         $USER_NAME"
    display_line "  User Shell:        $USER_SHELL"
    display_line ""

    # --- 5. PACMAN AND SOFTWARE (Array Handling) ---
    display_line "### 📦 SOFTWARE & BOOT ###"
    display_line "  Bootloader:        $BOOTLOADER"
    display_line ""

    # --- 6. HARDWARE DETECTED ---
    display_line "### 🖥️  HARDWARE DETECTION ###"
    display_line "  CPU:              $HARDWARE_CPU"
    display_line "  GPU:              $HARDWARE_GPU"
    display_line "  3D Support:       $HARDWARE_3D"
    display_line "  Virtual:          $HARDWARE_VIRTUAL"
    display_line ""

    # Safely list Base Packages
    if [ ${#BASE_PACKAGES[@]} -gt 0 ]; then
        display_line "  Base Packages:     ${BASE_PACKAGES[*]}"
    else
        display_line "  Base Packages:     (Empty or not defined)"
    fi

    # Safely list Common Packages
    if [ ${#COMMON_PACKAGES[@]} -gt 0 ]; then
        display_line "  Common Packages:   ${COMMON_PACKAGES[*]}"
    else
        display_line "  Common Packages:   (Empty or not defined)"
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
        display_info "=== Hardware Recommendations ==="
        for rec in "${recommendations[@]}"; do
            display_info "  • $rec"
        done
        display_info "================================="
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
            display_warning "Password cannot be empty. Please try again."
        elif [ "$pass1" != "$pass2" ]; then
            display_critical "Passwords do not match. Please try again."
        else
            display_success "${account_type} password successfully set."
            # Return the password by echoing it to stdout
            echo "$pass1"
            return 0 # Success
        fi

        # We only return 1 if the user hits Ctrl+C or a critical error occurs,
        # otherwise the loop handles retries.
    done
    return 1 # Should only be reached if loop is broken unexpectedly
}

### = run: run a command with status indicators and log outputs (with spinner)
function run() {
    # 1. Function Setup and Variable Declaration
    local command="$1"
    local pid
    local status=0

    # SECURITY ENHANCEMENT: Command Sanitization for Display/Logging ---
    # Sanitize the command string for display and non-error logging.
    # This uses sed with extended regex (-E) to replace the password argument (the quoted string)
    # in patterns like 'echo -n '...password...' | ...' with '[SECRET]'.

    # Pattern groups:
    # 1. (echo -[a-z]*)       : Captures 'echo -n', 'echo -e', etc.
    # 2. ([[:space:]]+)       : Captures one or more spaces.
    # 3. (\"[^\"]+\"|'[^']+') : Captures the content inside double quotes or single quotes (the secret).
    # Replacement: \1\2[SECRET] - Puts back Group 1, Group 2, and the placeholder.
    local sanitized_command
    sanitized_command=$(
        echo "$command" | sed -E "s/(echo -[a-z]*)([[:space:]]+)(\"[^\"]+\"|'[^']+')/\1\2[SECRET]/g"
    )

    # Use the sanitized version for display and feedback logging
    local display_text="$sanitized_command"

    # Create a unique temporary file path for output capture.
    local temp_output
    temp_output=$(mktemp)

    # 2. Log Command to COMMAND_LOG (Start of command execution record)
    echo "$sanitized_command" >> "$COMMAND_LOG"

    # 3. Display Running Status (uses sanitized text)
    display_running "$display_text"

    # 4. Execute Command in Background, when not in dry run
    # Send all stdout/stderr (2>&1) to the temporary file for capture.
    # The eval is necessary for robust execution of the single command string argument.
    if [ "$DRYRUN" -eq 0 ]; then
        eval "$command" > "$temp_output" 2>&1 &
        pid=$!

        # 5. Show Spinner and Wait for Completion
        show_spinner "$pid" "$display_text"

        # Wait for the background process and capture its exit status
        wait "$pid"
        status=$?
    fi

    # 6. Process Logs (ERROR_LOG - The Master Log)
    # ERROR_LOG contains all commands, command output, and errors.
    echo "--- START: $display_text (PID: $pid, Status: $status) ---" >> "$ERROR_LOG"
    cat "$temp_output" >> "$ERROR_LOG"
    # echo "--- END: $display_text ---" >> "$ERROR_LOG"

    # 7. Conditional TTY Output (VERBOSE=1)
    if [ "$VERBOSE" -eq 1 ]; then
        # If verbose, display the captured output to the TTY
        if [ -s "$temp_output" ]; then
            echo -e "\n[ Command Output Start ]"
            cat "$temp_output"
            echo -e "[ Command Output End ]\n"
        fi
    fi

    # 8. Check Status and Exit on Failure
    if [ "$status" -eq 0 ]; then
        # Success path
        display_completed "$display_text"
        rm -f "$temp_output"
    else
        # Failure path: Log error details, display critical message, and exit.

        # Append error output/status to COMMAND_LOG
        echo "Command FAILED (Exit Code: $status). Error output captured below:" >> "$COMMAND_LOG"
        cat "$temp_output" >> "$COMMAND_LOG"

        # Display failure status (uses sanitized text)
        display_failed "$display_text"
        display_critical "Command failed for: $display_text (Exit Code $status). See $ERROR_LOG for full output and $COMMAND_LOG for errors."

        # Cleanup temp file and exit the script
        rm -f "$temp_output"
        exit EXIT_COMMAND_ERROR
    fi
}

### = run_chroot: run a command in the target system
#####################################################################
# Function: run_chroot
# Description: Executes a shell command inside the Arch-chroot environment,
#              supporting piped input from the host system. It handles command
#              sanitization, logging, progress display (spinner), error checking,
#              and exits the script on command failure.
#
# Assumptions:
#   - Global variable $MOUNT_POINT is set to the mount point (e.g., /mnt).
#   - Supporting functions (display_running, show_spinner, display_completed,
#     display_failed, display_critical) and global variables ($COMMAND_LOG,
#     $ERROR_LOG, $DRYRUN, $VERBOSE) are defined.
#
# Arguments:
#   $1 - The shell command string to be executed *inside* the chroot (e.g., 'useradd -m user').
#   $2 - (Optional) The string content to be piped into the chroot command's stdin
#        (e.g., a password for 'chpasswd').
#
# Usage Example (Changing a password):
#   run_chroot "chpasswd" "user:newsecretpassword"
#
# Usage Example (Regular command):
#   run_chroot "pacman -Syu --noconfirm" ""
#
# Returns:
#   0 - Success.
#   Exits the script with EXIT_COMMAND_ERROR on any non-zero exit status from the
#   executed chroot command, or EXIT_SETUP_ERROR if $CHROOT_DIR is invalid.
#####################################################################
function run_chroot() {
    # 1. Function Setup and Variable Declaration
    local command="$1"      # The shell command to run *inside* the chroot
    local pipe_input="$2"   # The string to be piped into the command (can be empty)
    local pid
    local status=0

    # Sanity check for chroot directory
    if [ -z "${MOUNT_POINT}" ] || [ ! -d "${MOUNT_POINT}" ]; then
        display_critical "CHROOT_DIR is not set or not a valid directory. Cannot run arch-chroot."
        exit EXIT_SETUP_ERROR
    fi

    # 2. Command Construction for Execution
    # The actual command to be executed on the *host* system, which wraps the user's command
    local full_host_command="arch-chroot ${MOUNT_POINT} $command"

    # If pipe input is provided, prepend it to the full command string using 'echo' and ' | '
    if [ -n "$pipe_input" ]; then
        # IMPORTANT: Use 'printf' to avoid issues with potential shell expansions in 'echo -n'
        # The complete command to be evaluated will look like:
        # printf 'pipe_input' | arch-chroot /mnt 'chpasswd ...'
        full_host_command="printf '%s' \"$pipe_input\" | $full_host_command"
    fi

    # 3. Security Enhancement & Display Setup (Same as 'run')
    # Sanitize the command string for display and non-error logging
    # Note: This sanitizes the *pipe_input* if it contains the echo pattern, which is correct
    local sanitized_command
    sanitized_command=$(
        echo "$full_host_command" | sed -E "s/(echo -[a-z]*|[pP]rintf[[:space:]]+)(\"[^\"]+\"|'[^']+')/\1[SECRET]/g"
    )
    # Adjusted regex to also catch 'printf '...'' and simplify the capture groups
    # Note: If pipe_input is a secret, it will be the argument to 'printf', and this needs sanitation.
    # We use a placeholder 'printf[[:space:]]+' to catch the start of the piped secret.

    # Use the sanitized version for display and feedback logging
    local display_text="$sanitized_command"

    # Create a unique temporary file path for output capture.
    local temp_output
    temp_output=$(mktemp)

    # 4. Log Command to COMMAND_LOG (Start of command execution record)
    echo "$sanitized_command" >> "$COMMAND_LOG"

    # 5. Display Running Status (uses sanitized text)
    display_running "$display_text"

    # 6. Execute Command in Background, when not in dry run
    if [ "$DRYRUN" -eq 0 ]; then
        # Use eval to robustly execute the full_host_command (which may contain a pipe)
        # Send all stdout/stderr (2>&1) to the temporary file for capture.
        eval "$full_host_command" > "$temp_output" 2>&1 &
        pid=$!

        # 7. Show Spinner and Wait for Completion
        show_spinner "$pid" "$display_text"

        # Wait for the background process and capture its exit status
        wait "$pid"
        status=$?
    fi

    # 8. Process Logs (ERROR_LOG - The Master Log)
    echo "--- START: $display_text (PID: $pid, Status: $status) ---" >> "$ERROR_LOG"
    cat "$temp_output" >> "$ERROR_LOG"
    # echo "--- END: $display_text ---" >> "$ERROR_LOG"

    # 9. Conditional TTY Output (VERBOSE=1)
    if [ "$VERBOSE" -eq 1 ]; then
        if [ -s "$temp_output" ]; then
            echo -e "\n[ Chroot Command Output Start ]"
            cat "$temp_output"
            echo -e "[ Chroot Command Output End ]\n"
        fi
    fi

    # 10. Check Status and Exit on Failure
    if [ "$status" -eq 0 ]; then
        # Success path
        display_completed "$display_text"
        rm -f "$temp_output"
    else
        # Failure path: Log error details, display critical message, and exit.

        # Append error output/status to COMMAND_LOG
        echo "Chroot Command FAILED (Exit Code: $status). Error output captured below:" >> "$COMMAND_LOG"
        cat "$temp_output" >> "$COMMAND_LOG"

        # Display failure status (uses sanitized text)
        display_failed "$display_text"
        display_critical "Chroot command failed for: $display_text (Exit Code $status). See $ERROR_LOG for full output and $COMMAND_LOG for errors."

        # Cleanup temp file and exit the script
        rm -f "$temp_output"
        exit EXIT_COMMAND_ERROR
    fi
}

## Setup script logic
### - parse_arguments: Set variables depending on arguments passed
parse_arguments() {
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
                display_critical "Unknown option: $1"
                display_help
                ;;
        esac
    done
}


### Get the passwords for user and LUKS
function get_user_info() {
    display_info "Please provide passwords for the main user and luks vault"
    # USER_PASSWORD=$(get_password "$USER_NAME" "Enter password") || exit 1
    # LUKS_PASSWORD=$(get_password "Luks" "Enter password") || exit 1
}

## Device and Partition functions
### = device_reset: - Clear device, partitions, randomise, etc
function device_reset() {

    # Wipe partition table and inform the operating system
    run "wipefs -af $TARGET_DISK"
    run "sgdisk --zap-all --clear $TARGET_DISK"
    run "partprobe ${TARGET_DISK}"

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
    # - Partition 1 - EFI partition (ESP) - size 1024MiB, code ef00
    # - Partition 2 - encrypted partition (LUKS) - remaining storage, code 8309
    # - Note - the Discoverable Partition Specifications mentions 8304 for root
    run "sgdisk -n 0:0:+1024MiB -t 0:ef00 -c 0:EFI $TARGET_DISK"
    run "sgdisk -n 0:0:0 -t 0:8304 -c 0:LUKS $TARGET_DISK"
    run "partprobe ${TARGET_DISK}"
}

### = device_encrypt_root - Encrypt root partition
function device_encrypt_root() {

    # Encrypt root partition with LUKS 2
    # When systemd runs in the initial RAM disk (initrd) and detects a root partition
    # with a recognized architecture-specific root GPT GUID that is LUKS-encrypted,
    # it will open the volume with the name root, creating the device node at /dev/mapper/root
    run "echo -n '$LUKS_PASSWORD' | cryptsetup luksFormat --label ${LUKS_NAME} ${ROOT_PARTITION}"
    run "echo -n '$LUKS_PASSWORD' | cryptsetup luksOpen ${ROOT_PARTITION} ${LUKS_NAME}"
}

### = device_partitions_format
function device_partitions_format() {
    # Format the EFI partition with vfat
    run "mkfs.vfat -F32 -n EFI $EFI_PARTITION"

    # Format the encrypted root partition with BTRFS
    run "mkfs.btrfs -f -L ${LUKS_NAME} /dev/mapper/${LUKS_NAME}"
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
    # - @home -- /home (preserve user data)
    # - @snapshots -- /.snapshots
    # - @cache -- /var/cache
    # - @libvirt -- /var/lib/libvirt (virtual machine images)
    # - @log -- /var/log (excluding log files makes troubleshooting easier after reverting /)
    # - @tmp -- /var/tmp
    # The reasoning behind not excluding the entire /var out of the root snapshot is that /var/lib/pacman database in particular should mirror the rolled back state of installed packages.
    run "btrfs subvolume create ${MOUNT_POINT}/@home"
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

    # Note the -t btrfs is just to specify the filesystem type and help shell completion. The subvol option specifies which subvolume to mount.
    # Also note that the mount '-m' command creates the mount point if it does not already exist (${MOUNT_POINT}/home, etc )
    # Compression is enabled with zstd, which saves space and can improve performance. The zstd:1 means compression level 1 (range 1-5, default 3).
    # According to Arch Wiki, level 1 improves fragmentation and reduces IO, potentially improving performance.
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@ -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@home -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/home"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@cache -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/cache"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@log -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/log"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@tmp -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/tmp"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@snapshots -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/.snapshots"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@libvirt -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/libvirt"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@docker -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/docker"

    # Note that disabling CoW will simultaneously disable Btrfs snapshotting, data checksumming, and compression.
    # This is mainly to avoid frequent writes on directories like log, cache, tmp, and var/tmp which generally do not need snapshots.
    # Also, docker, podman, and libvirt use their own image formats, and using CoW may cause performance issues.
    run "chattr +C ${MOUNT_POINT}/var/lib/libvirt"
    run "chattr +C ${MOUNT_POINT}/var/lib/docker"
}

### = device_partitions_mount: - Helper function to mount existing install
function device_partitions_mount() {

    # Open the root partiton (LUKS)
    run "echo -n '$LUKS_PASSWORD' | cryptsetup luksOpen ${ROOT_PARTITION} ${LUKS_NAME}"

    # Mount root and root sub-volumes
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@ -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@home -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/home"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@cache -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/cache"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@log -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/log"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@tmp -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/tmp"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@snapshots -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/.snapshots"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@libvirt -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/libvirt"
    run "mount -t btrfs -o ${BTRFS_OPTIONS},subvol=@docker -m /dev/mapper/${LUKS_NAME} ${MOUNT_POINT}/var/lib/docker"

    # Mount efi
    run "mount -m ${EFI_PARTITION} ${MOUNT_POINT}/efi"
}

## Linux Installation functions
### = install_disk: Configure disks and partitions
function install_disk() {
    ### Install Disk Configuration
    display_section "Install Disk Configuration"

    device_reset
    device_partitions_create
    device_encrypt_root
    device_partitions_format
    device_btrfs_subvolumes_create
    device_btrfs_subvolumes_mount

    # Mount EFI partition:
    run "mount -m ${EFI_PARTITION} ${MOUNT_POINT}/efi"
}

### = install_linux_base: Pacstrap Arch Linux base (minimal)
install_linux_base() {
    ### Install Linux OS packages
    display_section "Install Arch Linux - base"

    ### Reflector
    # Before installation, use the reflector command to update mirror lists. Replace --country with your country or a nearby one.
    run "reflector --country ${SYSTEM_COUNTRY} --latest 10 --age 24 --protocol http,https --sort rate --save /etc/pacman.d/mirrorlist"

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
    run "genfstab -U ${MOUNT_POINT} >> ${MOUNT_POINT}/etc/fstab"

    # Clean up the created files
    run "rm -f PACKAGES_HARDWARE LINUX_BASE"
}

### = install_firstboot: Configure Arch linux to user locations
function install_firstboot() {

    # Set the language characters
    # Note when debugging the file might not exist

    if [[ -f "${MOUNT_POINT}/etc/locale.gen" ]]; then
        run "sed -i -e "/^#${SYSTEM_LOCALE}/s/^#//" ${MOUNT_POINT}/etc/locale.gen"
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
    run "echo -n '--locale=${SYSTEM_LOCALE} ' >> FIRSTBOOT"
    run "echo -n '--keymap=${KEYMAP} ' >> FIRSTBOOT"
    run "echo -n '--timezone=${TIME_ZONE} ' >> FIRSTBOOT"
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
    run "arch-chroot ${MOUNT_POINT} locale-gen"
}

### = install_user: Configure main user
function install_user() {

    # Note bob and donlad work

    # 1. Create the user, with root privileges and home directory
    run "arch-chroot ${MOUNT_POINT} useradd -G wheel -s ${USER_SHELL} -m ${USER_NAME}"

    # 2. Change the main user password using a hashed password
    # Use /bin/bash -c to execute the pipeline entirely inside the chroot.
    # run "arch-chroot ${MOUNT_POINT} /bin/bash -c \"echo '${USER_NAME}:${USER_PASS_HASHED}' | chpasswd -e\""

    # # Creating the password without run - to bypass any issues on piping
    # echo -n "${USER_NAME}:${USER_PASS_HASHED}" | arch-chroot ${MOUNT_POINT} chpasswd -e

    # # 1. Create the user, with root privileges and home directory
    # run "arch-chroot ${MOUNT_POINT} useradd -G wheel -s ${USER_SHELL} -m bob"
    # echo -n "bob:123" | arch-chroot ${MOUNT_POINT} chpasswd

    # 1. Create the user, with root privileges and home directory
    run "arch-chroot ${MOUNT_POINT} useradd -G wheel -s ${USER_SHELL} -m donald"
    run "echo -n 'donald:123' | arch-chroot ${MOUNT_POINT} chpasswd"

    local USER_NAME2=echjansen2
    # Lets try the run_chroot function
    run_chroot "useradd -G wheel -s ${USER_SHELL} -m ${USER_NAME2}"
    run_chroot "chpasswd -e" "${USER_NAME2}:${USER_PASS_HASHED}"

    local USER_NAME3=echjansen3
    # Lets try the run_chroot function
    run_chroot "useradd -G wheel -s ${USER_SHELL} -m ${USER_NAME3}"
    run_chroot "chpasswd" "${USER_NAME3}:${USER_PASSWORD}"

    # Allow the WHEEL group to run sudo commands, without providing password
    run "cp -f rootfs/etc/sudoers ${MOUNT_POINT}/etc/sudoers"
}

### = install_uki: Configure Universal Kernel Images
function install_uki() {

    # Create the folder for the kernel images
    run "mkdir -p ${MOUNT_POINT}/efi/EFI/Linux"

    # Set the kernel commands line
    run "echo -n 'quiet rw' > ${MOUNT_POINT}/etc/kernel/cmdline"
    # run "echo -n 'rw' > ${MOUNT_POINT}/etc/kernel/cmdline"

    # Because we are using sub volumes, to root has changed from default / to @
    # Tell that the root is the @ btrfs sub-volume
    run "echo -n ' rootflags=subvol=@' >> ${MOUNT_POINT}/etc/kernel/cmdline"

    # Copy the kernel configuration
    run "cp -f rootfs/etc/mkinitcpio.d/linux.preset ${MOUNT_POINT}/etc/mkinitcpio.d/linux.preset"

    # Copy the mkinitcpio configuration (HOOKS updated)
    run "cp -f rootfs/etc/mkinitcpio.conf ${MOUNT_POINT}/etc/mkinitcpio.conf"

    # Generate kernel images
    run "arch-chroot ${MOUNT_POINT} mkinitcpio -P"
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
    run "arch-chroot -S ${MOUNT_POINT} bootctl install"
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

    display_section "Installation Review"
    display_info "The following key configuration files were created or modified."
    display_info "You may review their content before rebooting."
    display_info "==============================================================="

    local SKIP_ALL_REVIEWS=false
    read -r -p "Do you want to **review** the installation? (Y/n, or S to skip all) [Y/n/S] " initial_choice

    case "$initial_choice" in
        [nN])
            display_info "Skipping all reviews based on your request."
            return # Exit the function immediately
            ;;
        [sS])
            display_info "Skipping all reviews based on your request."
            return # Exit the function immediately
            ;;
        [yY]*|"")
            # Continue with the individual prompts
            display_info "Proceeding with individual file/directory reviews..."
            ;;
        *)
            # Invalid choice, default to proceeding with individual prompts
            display_info "Invalid choice. Proceeding with individual file/directory reviews..."
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
                    echo -e "\n${GREEN}--- Content of ${FILE} ---${NC}"
                    # Use 'cat' for simple output, or 'less' for long files
                    # cat "$FULL_PATH"
                    more "$FULL_PATH"
                    display_info "--- END ---"
                    ;;
                [nN]*)
                    continue # Skip to the next file
                    ;;
                *)
                    echo "Invalid choice. Skipping."
                    ;;
            esac
        fi
    done

    for DIR in "${INSTALL_DIRS[@]}"; do
        local FULL_PATH="${ROOT_DIR}${DIR}"

        if [ -d "$FULL_PATH" ]; then
            read -r -p "List contents of ${DIR}? [Y/n] " choice

            case "$choice" in
                [yY]*|"")
                    echo -e "\n${GREEN}--- Listing contents of ${DIR} (ls -lah) ---${NC}"
                    # Use ls -lah for human-readable sizes and full details
                    ls -lah "$FULL_PATH"
                    echo -e "--- End of ${DIR} Listing ---\n"
                    ;;
                [nN]*)
                    continue
                    ;;
                *)
                    echo "Invalid choice. Skipping."
                    ;;
            esac
        else
            echo -e "${YELLOW}Warning:${NC} Directory ${DIR} does not exist. Skipping."
        fi
    done

    display_info "=== Review Complete ==="
}

## Main
main() {
    clear
    init_logging
    detect_hardware
    display_config
    parse_arguments "$@"
    load_config "$CONFIG_FILE"
    validate_config
    preflight_checks

    # Confirm before proceeding
    if [[ "$DRYRUN" -eq 0 ]]; then
        input_info "Proceed with installation? [y/N]: "
        read -r confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
    fi

    # Main installation logic would go here
    get_user_info
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

# Just mount he installed system
# device_partitions_mount
