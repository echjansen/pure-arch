#!/bin/bash
set -euo pipefail               # Exit on errors, etc

# -----------------------------------------------------------------------------
# Script: pure-linux-detect.sh
# Description: (Arch) Linux host detections
# Author: echjansen
# Date: 2025-11-08
# Version: 0.0.0
# -----------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Common Linux Hardware and Location detections
#------------------------------------------------------------------------------
# Features
# - [X] SYSTEM_CPU (Intel, AMD)
# - [X] SYSTEM_CPU_DRIVERS
# - [X] SYSTEM_GPU (Intel, NVIDIA, AMD)
# - [X] SYSTEM_GPU_DRIVERS
# - [X] SYSTEM_VIRT (VirtualBox, KVM/QEMU, VMware, Hyper-V, Container, BareMetal
# - [X] SYSTEM_VIRT_DRIVERS
# - [X] SYSTEM_COUNTRY_CODE (AU, US, etc)
# - [X] SYSTEM_LOCALE (en_AU.UTF-8, etc)
# - [X] SYSTEM_KEYMAP (us, etc)
# - [X] SYSTEM_ROOT_PERMS (Yes, No)
# - [X] SYSTEM_UEFI_MODE (Yes, No)
# - [X] SYSTEM_TPM2_AVAIL (Yes, No)
# - [X] SYSTEM_TPM2_SETUP_MODE (Yes, No)
#------------------------------------------------------------------------------

# # Note: Support for VirtualBox
# pacman -Syu
# pacman -S virtualbox-guest-utils
# pacman -S linux-headers # Ensure kernel headers are present
# systemctl enable vboxservice.service
# systemctl start vboxservice.service
# gpasswd -a your_username vboxsf # For shared folders
# reboot

# Set to 'true' for open-source drivers (default and generally recommended).
# Set to 'false' if you explicitly want proprietary drivers (e.g., NVIDIA, but be aware of complications).
SYSTEM_OPENSOURCE="true" # Can be changed to "false" by the user before running or via export

# Initialize variables to 'Unknown'
SYSTEM_CPU="Unknown"
SYSTEM_GPU="Unknown"
SYSTEM_VIRT="Unknown"
SYSTEM_COUNTRY_CODE="Unknown"
SYSTEM_LOCALE="Unknown"
SYSTEM_KEYMAP="Unknown"
SYSTEM_ROOT_PERMS="Unknown"
SYSTEM_UEFI_MODE="Unknown"
SYSTEM_TPM2_AVAIL="Unknown"
SYSTEM_TPM2_SETUP_MODE="Unknown"

# Variables for package lists
SYSTEM_CPU_DRIVERS=""
SYSTEM_GPU_DRIVERS=""
SYSTEM_VIRT_DRIVERS=""

### = detect_cpu: Detect CPU information
get_cpu() {
    local cpu_vendor_id=$(lscpu 2>/dev/null | grep 'Vendor ID' | awk '{print $3}')

    case "$cpu_vendor_id" in
        "GenuineIntel") SYSTEM_CPU="Intel" ;;
        "AuthenticAMD") SYSTEM_CPU="AMD" ;;
        *) SYSTEM_CPU="Other" ;;
    esac
}

## Function to detect GPU information
get_gpu() {
    # Check for "VGA compatible controller" and then filter by vendor
    if lspci -k 2>/dev/null | grep -i 'VGA compatible controller' | grep -i 'nvidia' &> /dev/null; then
        SYSTEM_GPU="NVIDIA"
    elif lspci -k 2>/dev/null | grep -i 'VGA compatible controller' | grep -i 'amd' &> /dev/null; then
        SYSTEM_GPU="AMD"
    elif lspci -k 2>/dev/null | grep -i 'VGA compatible controller' | grep -i 'intel' &> /dev/null; then
        SYSTEM_GPU="Intel"
    # Add checks for virtualized GPUs
    elif lspci -k 2>/dev/null | grep -i 'VGA compatible controller' | grep -i 'VMware' &> /dev/null; then
        SYSTEM_GPU="VMware"
    elif lspci -k 2>/dev/null | grep -i 'VGA compatible controller' | grep -i 'VirtualBox' &> /dev/null; then
        SYSTEM_GPU="VirtualBox"
    else
        SYSTEM_GPU="Unknown"
    fi
}

## Function to detect Virtualization
get_virtualization() {
    if systemd-detect-virt &> /dev/null; then
        local virt_type=$(systemd-detect-virt)
        if [ "$virt_type" != "none" ]; then
            case "$virt_type" in
                "kvm"|"qemu") SYSTEM_VIRT="KVM/QEMU" ;;
                "vmware") SYSTEM_VIRT="VMware" ;;
                "microsoft") SYSTEM_VIRT="Hyper-V" ;;
                "oracle") SYSTEM_VIRT="VirtualBox" ;;
                "lxc"|"systemd-nspawn") SYSTEM_VIRT="Container" ;;
                *) SYSTEM_VIRT="$virt_type" ;;
            esac
        else
            SYSTEM_VIRT="BareMetal"
        fi
    else
        # Fallback if systemd-detect-virt is not available
        if grep -q vmx /proc/cpuinfo 2>/dev/null || grep -q svm /proc/cpuinfo 2>/dev/null; then
            if dmidecode -s system-product-name 2>/dev/null | grep -i -E 'vmware|virtualbox|parallels|hyper-v|qemu' &> /dev/null; then
                local product_name=$(dmidecode -s system-product-name 2>/dev/null | head -n 1)
                case "$product_name" in
                    *VMware*) SYSTEM_VIRT="VMware" ;;
                    *VirtualBox*) SYSTEM_VIRT="VirtualBox" ;;
                    *Parallels*) SYSTEM_VIRT="Parallels" ;;
                    *Hyper-V*) SYSTEM_VIRT="Hyper-V" ;;
                    *QEMU*) SYSTEM_VIRT="KVM/QEMU" ;;
                    *) SYSTEM_VIRT="GenericVM" ;;
                esac
            else
                SYSTEM_VIRT="BareMetal/UnknownVM"
            fi
        else
            SYSTEM_VIRT="BareMetal"
        fi
        if [ -f /proc/modules ] && grep -q 'virtio' /proc/modules; then
            if [ "$SYSTEM_VIRT" == "BareMetal" ] || [ "$SYSTEM_VIRT" == "BareMetal/UnknownVM" ]; then
                SYSTEM_VIRT="GenericVM"
            fi
        fi
    fi
}

## Function to detect the country via IP geolocation
get_country() {
    # Check if curl is available
    if ! command -v curl &> /dev/null; then
        return 1 # Indicate failure, SYSTEM_COUNTRY_CODE remains "Unknown"
    fi

    # Try ipinfo.io first (simple country code output)
    local country_code=$(curl -s --max-time 5 https://ipinfo.io/country 2>/dev/null)

    if [ -n "$country_code" ]; then
        SYSTEM_COUNTRY_CODE="$country_code"
    else
        # Try ip-api.com (requires jq to parse JSON)
        if command -v jq &> /dev/null; then
            local ip_api_response=$(curl -s --max-time 5 http://ip-api.com/json/?fields=countryCode 2>/dev/null)
            if [ -n "$ip_api_response" ]; then
                country_code=$(echo "$ip_api_response" | jq -r '.countryCode' 2>/dev/null)
                if [ -n "$country_code" ] && [ "$country_code" != "null" ]; then
                    SYSTEM_COUNTRY_CODE="$country_code"
                fi
            fi
        fi
    fi
}

## Function to determine recommended locale based on country code
get_locale() {
    if [ "$SYSTEM_COUNTRY_CODE" == "Unknown" ]; then
        SYSTEM_LOCALE="Unknown" # Cannot determine without country
        return 1
    fi

    case "$SYSTEM_COUNTRY_CODE" in
        "US") SYSTEM_LOCALE="en_US.UTF-8" ;;
        "GB") SYSTEM_LOCALE="en_GB.UTF-8" ;;
        "CA") SYSTEM_LOCALE="en_CA.UTF-8" ;;
        "AU") SYSTEM_LOCALE="en_AU.UTF-8" ;;
        "NZ") SYSTEM_LOCALE="en_NZ.UTF-8" ;;
        "IE") SYSTEM_LOCALE="en_IE.UTF-8" ;;
        "SG") SYSTEM_LOCALE="en_SG.UTF-8" ;;
        "DE") SYSTEM_LOCALE="de_DE.UTF-8" ;;
        "FR") SYSTEM_LOCALE="fr_FR.UTF-8" ;;
        "ES") SYSTEM_LOCALE="es_ES.UTF-8" ;;
        "IT") SYSTEM_LOCALE="it_IT.UTF-8" ;;
        "JP") SYSTEM_LOCALE="ja_JP.UTF-8" ;;
        "KR") SYSTEM_LOCALE="ko_KR.UTF-8" ;;
        "CN") SYSTEM_LOCALE="zh_CN.UTF-8" ;;
        "TW") SYSTEM_LOCALE="zh_TW.UTF-8" ;;
        "HK") SYSTEM_LOCALE="en_HK.UTF-8" ;;
        "IN") SYSTEM_LOCALE="en_IN.UTF-8" ;;
        "RU") SYSTEM_LOCALE="ru_RU.UTF-8" ;;
        "BR") SYSTEM_LOCALE="pt_BR.UTF-8" ;;
        "MX") SYSTEM_LOCALE="es_MX.UTF-8" ;;
        "AR") SYSTEM_LOCALE="es_AR.UTF-8" ;;
        "DK") SYSTEM_LOCALE="da_DK.UTF-8" ;;
        "SE") SYSTEM_LOCALE="sv_SE.UTF-8" ;;
        "NO") SYSTEM_LOCALE="nb_NO.UTF-8" ;;
        "FI") SYSTEM_LOCALE="fi_FI.UTF-8" ;;
        "NL") SYSTEM_LOCALE="nl_NL.UTF-8" ;;
        "BE") SYSTEM_LOCALE="en_BE.UTF-8" ;;
        "AT") SYSTEM_LOCALE="de_AT.UTF-8" ;;
        "CH") SYSTEM_LOCALE="en_CH.UTF-8" ;;
        "PL") SYSTEM_LOCALE="pl_PL.UTF-8" ;;
        "CZ") SYSTEM_LOCALE="cs_CZ.UTF-8" ;;
        "HU") SYSTEM_LOCALE="hu_HU.UTF-8" ;;
        "RO") SYSTEM_LOCALE="ro_RO.UTF-8" ;;
        "GR") SYSTEM_LOCALE="el_GR.UTF-8" ;;
        "TR") SYSTEM_LOCALE="tr_TR.UTF-8" ;;
        "ZA") SYSTEM_LOCALE="en_ZA.UTF-8" ;;
        *) SYSTEM_LOCALE="en_US.UTF-8" ;; # Default fallback
    esac
}

## Function to determine recommended keymap based on country code
get_keymap() {
    if [ "$SYSTEM_COUNTRY_CODE" == "Unknown" ]; then
        SYSTEM_KEYMAP="Unknown" # Cannot determine without country
        return 1
    fi

    case "$SYSTEM_COUNTRY_CODE" in
        "US"|"CA"|"AU"|"NZ"|"IE"|"GB"|"SG") SYSTEM_KEYMAP="us" ;;
        "DE"|"AT") SYSTEM_KEYMAP="de" ;;
        "FR") SYSTEM_KEYMAP="fr" ;;
        "ES") SYSTEM_KEYMAP="es" ;;
        "IT") SYSTEM_KEYMAP="it" ;;
        "JP") SYSTEM_KEYMAP="jp" ;;
        "KR") SYSTEM_KEYMAP="kr" ;;
        "CN"|"TW"|"HK"|"IN"|"ZA") SYSTEM_KEYMAP="us" ;; # Common English/US default for these regions
        "RU") SYSTEM_KEYMAP="ru" ;;
        "BR") SYSTEM_KEYMAP="br-abnt2" ;;
        "MX"|"AR") SYSTEM_KEYMAP="la" ;;
        "DK") SYSTEM_KEYMAP="dk" ;;
        "SE") SYSTEM_KEYMAP="se" ;;
        "NO") SYSTEM_KEYMAP="no" ;;
        "FI") SYSTEM_KEYMAP="fi" ;;
        "NL") SYSTEM_KEYMAP="us" ;;
        "BE") SYSTEM_KEYMAP="be" ;;
        "CH") SYSTEM_KEYMAP="ch" ;;
        "PL") SYSTEM_KEYMAP="pl" ;;
        "CZ") SYSTEM_KEYMAP="cz" ;;
        "HU") SYSTEM_KEYMAP="hu" ;;
        "RO") SYSTEM_KEYMAP="ro" ;;
        "GR") SYSTEM_KEYMAP="gr" ;;
        "TR") SYSTEM_KEYMAP="tr" ;;
        *) SYSTEM_KEYMAP="us" ;; # Default fallback
    esac
}

## Function to detect root permissions
get_root_permissions() {
    if [ "$EUID" -eq 0 ]; then
        SYSTEM_ROOT_PERMS="Yes"
    else
        SYSTEM_ROOT_PERMS="No"
    fi
}

## Function to detect UEFI enabled boot
get_uefi_enabled() {
    if [ -d /sys/firmware/efi ]; then
        SYSTEM_UEFI_MODE="Yes"
    else
        SYSTEM_UEFI_MODE="No"
    fi
}

## Function to detect TPM2 available
get_tpm2_available() {
    # Check for TPM device nodes and TPM2 version in sysfs
    if [ -c /dev/tpm0 ] || [ -c /dev/tpmrm0 ]; then
        # Check if it's TPM2.0 specifically via sysfs
        local tpm_major_version=$(cat /sys/class/tpm/tpm0/tpm_version_major 2>/dev/null)
        if [ "$tpm_major_version" == "2" ]; then
            SYSTEM_TPM2_AVAIL="Yes"
        else
            SYSTEM_TPM2_AVAIL="No (TPM1.2 or other)" # TPM detected but not 2.0
        fi
    else
        SYSTEM_TPM2_AVAIL="No"
    fi
}

## Function to detect TPM2 in setup mode (or unowned/cleared)
get_tpm2_setup_mode() {
    if [ "$SYSTEM_TPM2_AVAIL" != "Yes" ]; then
        SYSTEM_TPM2_SETUP_MODE="N/A (TPM2 not available)"
        return 1
    fi

    # Without tpm2-tools, directly detecting "setup mode" (TPM_ST_CLEAR) is hard.
    # We can check if it's enabled and active.
    # If the TPM is enabled and active, but not owned, it's generally considered
    # ready for setup/provisioning.
    local tpm_enabled=$(cat /sys/class/tpm/tpm0/enabled 2>/dev/null)
    local tpm_active=$(cat /sys/class/tpm/tpm0/active 2>/dev/null)
    local tpm_ownership=$(cat /sys/class/tpm/tpm0/owned 2>/dev/null) # Not always present or reliable without tpm2-tools

    if [ "$tpm_enabled" == "1" ] && [ "$tpm_active" == "1" ]; then
        # This is a pragmatic check. A truly "setup mode" TPM is often unowned.
        # However, checking 'owned' via sysfs is not standardized or always present.
        # If tpm2-tools were available, we'd use 'tpm2_getcap properties' to check ownership.
        if [ "$tpm_ownership" == "0" ]; then # If 'owned' sysfs is present and 0
             SYSTEM_TPM2_SETUP_MODE="Yes (Enabled, Active, Unowned)"
        elif [ "$tpm_ownership" == "1" ]; then
             SYSTEM_TPM2_SETUP_MODE="No (Enabled, Active, Owned)"
        else
             SYSTEM_TPM2_SETUP_MODE="Enabled, Active (Ownership Unknown without tpm2-tools)"
        fi
    elif [ "$tpm_enabled" == "0" ]; then
        SYSTEM_TPM2_SETUP_MODE="No (Disabled in BIOS/firmware)"
    else
        SYSTEM_TPM2_SETUP_MODE="Unknown (Check BIOS/firmware)"
    fi
}

## Function to get recommended CPU related packages
get_cpu_drivers() {
    local packages="linux-firmware " # linux-firmware is essential for most hardware
    case "$SYSTEM_CPU" in
        "Intel")
            packages+="intel-ucode " # Microcode for Intel CPUs
            ;;
        "AMD")
            packages+="amd-ucode " # Microcode for AMD CPUs
            ;;
        # For "Other" CPUs, microcode might not be necessary or handled differently
    esac
    SYSTEM_CPU_DRIVERS="$packages"
}

## Function to get recommended GPU related packages
get_gpu_drivers() {
    local packages="mesa " # Mesa is fundamental for 3D acceleration (OpenGL/Vulkan)
    case "$SYSTEM_GPU" in
        "NVIDIA")
            if [ "$SYSTEM_OPENSOURCE" == "true" ]; then
                packages+="xf86-video-nouveau lib32-mesa " # Nouveau (open-source) driver
            else
                packages+="nvidia nvidia-utils lib32-nvidia-utils " # Proprietary NVIDIA driver
                # Note: For specific kernel versions (e.g., LTS), use nvidia-lts, etc.
                # User might also need nvidia-dkms if using a custom kernel or headers.
            fi
            ;;
        "AMD")
            packages+="xf86-video-amdgpu vulkan-radeon lib32-mesa lib32-vulkan-radeon " # Modern AMDGPU driver
            # For older AMD GPUs, xf86-video-ati might be needed instead of or in addition to amdgpu.
            ;;
        "Intel")
            packages+="vulkan-intel lib32-mesa lib32-vulkan-intel " # Intel integrated graphics
            # xf86-video-intel is generally not needed for modern Intel GPUs (modesetting driver is default)
            ;;
        "Generic/Unknown")
            packages+="xf86-video-vesa " # Fallback drivers
            ;;
    esac
    SYSTEM_GPU_DRIVERS="$packages"
}

## Function to get recommended Virtualization guest packages
get_virt_drivers() {
    local packages=""
    case "$SYSTEM_VIRT" in
        "KVM/QEMU")
            packages+="qemu-guest-agent spice-vdagent " # For communication and display integration
            ;;
        "VMware")
            packages+="open-vm-tools " # VMware guest tools
            # xf86-video-vmware can be added for specific Xorg driver, but often not necessary
            ;;
        "Hyper-V")
            packages+="hyperv " # Kernel modules for Hyper-V (often built-in, but ensure present)
            # hyperv-daemon for enhanced services might be needed later
            ;;
        "VirtualBox")
            packages+="virtualbox-guest-utils " # VirtualBox guest utilities
            # xf86-video-vboxvideo can be added for specific Xorg driver, but often not necessary
            ;;
        # For BareMetal or Container, no specific virtualization guest packages are typically needed
    esac
    SYSTEM_VIRT_DRIVERS="$packages"
}

# --- Main Script Execution ---

echo "-------------------------------------"
echo "Hardware and Virtualization Detection"
echo "-------------------------------------"

# Call the functions to populate the variables
get_cpu
get_gpu
get_virtualization
get_country
get_locale
get_keymap
get_root_permissions
get_uefi_enabled
get_tpm2_available
get_tpm2_setup_mode

# Call the functions to get package lists
get_cpu_drivers
get_gpu_drivers
get_virt_drivers

# --- Detected System Information ---

echo ""
echo "--- Detected System Information ---"
echo "CPU Vendor:             $SYSTEM_CPU"
echo "GPU Vendor:             $SYSTEM_GPU"
echo "Virtualization Type:    $SYSTEM_VIRT"
echo "Detected Country Code:  $SYSTEM_COUNTRY_CODE"
echo "Recommended Locale:     $SYSTEM_LOCALE"
echo "Recommended Keymap:     $SYSTEM_KEYMAP"
echo "Root Permissions:       $SYSTEM_ROOT_PERMS"
echo "UEFI Boot Mode:         $SYSTEM_UEFI_MODE"
echo "TPM2.0 Available:       $SYSTEM_TPM2_AVAIL"
echo "TPM2.0 Setup Mode:      $SYSTEM_TPM2_SETUP_MODE"
echo "Open-Source Drivers:    $SYSTEM_OPENSOURCE"
echo "CPU-related Packages:   $SYSTEM_CPU_DRIVERS"
echo "GPU-related Packages:   $SYSTEM_GPU_DRIVERS"
echo "Virt-related Packages:  $SYSTEM_VIRT_DRIVERS"

# --- Summary and Export ---

echo ""
echo "Detection complete."
echo "-------------------------------------"

# Export variables so they are available in the current shell session
export SYSTEM_CPU
export SYSTEM_GPU
export SYSTEM_VIRT
export SYSTEM_COUNTRY_CODE
export SYSTEM_LOCALE
export SYSTEM_KEYMAP
export SYSTEM_ROOT_PERMS
export SYSTEM_UEFI_MODE
export SYSTEM_TPM2_AVAIL
export SYSTEM_TPM2_SETUP_MODE
export SYSTEM_OPENSOURCE
export SYSTEM_CPU_DRIVERS
export SYSTEM_GPU_DRIVERS
export SYSTEM_VIRT_DRIVERS
