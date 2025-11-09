#!/bin/bash
set -euo pipefail               # Exit on errors, etc

# -----------------------------------------------------------------------------
# Script: pure-linux-dialog.sh
# Description: Common dialogs for Linux installation
# Author: echjansen
# Date: 2025-11-08
# Version: 0.0.0
# -----------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Common Linux user settings queried via 'dialog'
#------------------------------------------------------------------------------
# Features
# - [X] Use dialog to select the $SYSTEM_CPU
# - [X] Use dialog to select the $SYSTEM_GPU
# - [X] Use dialog to select the $SYSTEM_VIRT
# -
# -
# -
# -
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Todo's
# - [X] Use dialog to select the $SYSTEM_CPU
# - [X] Use dialog to select the $SYSTEM_GPU
# - [X] Use dialog to select the $SYSTEM_VIRT
# - [ ] Use dialog to select the $DRIVE
# - [ ] Use dialog to select the $SYSTEM_COUNTRY (reflector)
# - [ ] Use dialog to select the $SYSTEM_LOCALE
# - [ ]
#------------------------------------------------------------------------------

# Function to display a menu using dialog and get user selection
# Arguments:
#   $1: Dialog title
#   $2: Dialog prompt/text
#   $3: Array of menu options (e.g., ("Option 1" "Description 1" "Option 2" "Description 2"))
# Returns: Selected option
dialog_menu() {
    local title="$1"
    local prompt="$2"
    shift 2
    local options=("$@")
    local selection

    selection=$(dialog --backtitle "Arch Linux Installation" \
                       --title "$title" \
                       --menu "$prompt" \
                       0 0 0 "${options[@]}" \
                       2>&1 >/dev/tty)

    echo "$selection"
}

# Function to display a checklist using dialog and get user selections
# Arguments:
#   $1: Dialog title
#   $2: Dialog prompt/text
#   $3: Array of checklist options (e.g., ("Item1" "Description1" "ON" "Item2" "Description2" "OFF"))
# Returns: Space-separated selected items
dialog_checklist() {
    local title="$1"
    local prompt="$2"
    shift 2
    local options=("$@")
    local selections

    selections=$(dialog --backtitle "Arch Linux Installation" \
                        --title "$title" \
                        --checklist "$prompt" \
                        0 0 0 "${options[@]}" \
                        2>&1 >/dev/tty)

    echo "$selections"
}


# Function to determine and select CPU drivers
get_cpu_drivers() {
    local cpu_drivers
    local cpu_selection
    local detected_cpu_info

    # Auto-detect CPU information
    if command -v lscpu &> /dev/null; then
        detected_cpu_info=$(lscpu | grep "Vendor ID" | awk '{print $3}')
        if [ -z "$detected_cpu_info" ]; then
            detected_cpu_info="Unknown CPU Vendor"
        fi
    else
        detected_cpu_info="lscpu not available (consider installing util-linux)"
    fi

    cpu_drivers=(
        "intel-ucode" "Microcode updates for Intel CPUs"
        "amd-ucode" "Microcode updates for AMD CPUs"
        "none_cpu" "No specific CPU microcode (not recommended)"
    )

    local prompt="Detected CPU Vendor: $detected_cpu_info\n\nSelect the microcode package for your CPU:"
    cpu_selection=$(dialog_menu "CPU Driver Selection" "$prompt" "${cpu_drivers[@]}")

    if [ -n "$cpu_selection" ]; then
        echo "$cpu_selection"
    else
        echo "none_cpu" # Default or fallback if selection is cancelled
    fi
}

# Function to determine and select GPU drivers
get_gpu_drivers() {
    local gpu_drivers
    local gpu_selection
    local detected_gpu_info

    # Auto-detect GPU information
    if command -v lspci &> /dev/null; then
        detected_gpu_info=$(lspci -k | grep -EA3 'VGA|3D|Display' | grep 'Kernel driver in use:' | awk -F': ' '{print $2}' | sort -u | paste -sd, -)
        if [ -z "$detected_gpu_info" ]; then
            detected_gpu_info=$(lspci | grep -EA3 'VGA|3D|Display' | grep -E 'VGA|3D|Display' | awk -F': ' '{print $NF}' | sort -u | paste -sd, -)
        fi
        if [ -z "$detected_gpu_info" ]; then
            detected_gpu_info="No specific GPU detected by lspci"
        fi
    else
        detected_gpu_info="lspci not available (consider installing pciutils)"
    fi

    gpu_drivers=(
        "nvidia" "NVIDIA proprietary drivers"
        "xf86-video-nouveau" "Open-source Nouveau driver for NVIDIA"
        "amdgpu" "Open-source AMDGPU driver for AMD GPUs"
        "xf86-video-amdgpu" "Legacy open-source driver for older AMD GPUs"
        "mesa" "Mesa 3D graphics library (often required with open-source drivers)"
        "intel" "Open-source Intel graphics drivers"
        "xf86-video-intel" "Legacy open-source driver for older Intel GPUs"
        "none_gpu" "No specific GPU driver (basic VESA, limited functionality)"
    )

    local prompt="Detected GPU(s): $detected_gpu_info\n\nSelect the graphics driver for your GPU. 'mesa' is often required alongside specific drivers:"
    gpu_selection=$(dialog_menu "GPU Driver Selection" "$prompt" "${gpu_drivers[@]}")

    if [ -n "$gpu_selection" ]; then
        echo "$gpu_selection"
    else
        echo "none_gpu" # Default or fallback if selection is cancelled
    fi
}

# Function to determine and select virtualizer drivers (if applicable)
get_virtualizer_drivers() {
    local virtualizer_drivers
    local virtualizer_selection
    local detected_virtualizer_info

    detected_virtualizer_info="Not detected"

    if grep -q "VBOX" /sys/firmware/acpi/tables/OEMB 2>/dev/null; then
        detected_virtualizer_info="VirtualBox"
    elif grep -q "VMware" /sys/firmware/acpi/tables/OEMB 2>/dev/null; then
        detected_virtualizer_info="VMware"
    elif dmesg | grep -qi "qemu"; then
        detected_virtualizer_info="QEMU/KVM"
    elif command -v systemd-detect-virt &> /dev/null && systemd-detect-virt -q; then
        detected_virtualizer_info=$(systemd-detect-virt)
    fi

    virtualizer_drivers=(
        "virtualbox-guest-utils" "Guest additions for VirtualBox virtual machines"
        "qemu-guest-agent" "QEMU Guest Agent for QEMU/KVM virtual machines"
        "open-vm-tools" "Open-VM-Tools for VMware virtual machines"
        "none_virt" "Not running in a virtual machine or no specific virtualizer drivers needed"
    )

    local prompt="Detected Virtualizer: $detected_virtualizer_info\n\nSelect drivers if installing in a virtual machine:"
    virtualizer_selection=$(dialog_menu "Virtualizer Driver Selection" "$prompt" "${virtualizer_drivers[@]}")

    if [ -n "$virtualizer_selection" ]; then
        echo "$virtualizer_selection"
    else
        echo "none_virt" # Default or fallback if selection is cancelled
    fi
}

# Function to select the timezone
select_timezone() {
    local timezone_selection
    local filter_input=""
    local filtered_timezones=()
    local timezone_list_raw

    if ! command -v timedatectl &> /dev/null; then
        dialog --msgbox "Error: timedatectl not found. Cannot list timezones." 5 50
        echo ""
        return
    fi

    timezone_list_raw=$(timedatectl list-timezones)

    while true; do
        filter_input=$(dialog --backtitle "Arch Linux Installation" \
                              --title "Timezone Filter" \
                              --inputbox "Enter a filter (e.g., 'Australia/Melbourne') or leave empty to show all:" \
                              0 0 "$filter_input" \
                              2>&1 >/dev/tty)

        if [ $? -ne 0 ]; then # User cancelled filter
            echo "" # Return empty selection for timezone
            return
        fi

        if [ -n "$filter_input" ]; then
            mapfile -t filtered_timezones < <(echo "$timezone_list_raw" | grep -i "$filter_input")
        else
            mapfile -t filtered_timezones < <(echo "$timezone_list_raw")
        fi

        if [ ${#filtered_timezones[@]} -eq 0 ]; then
            dialog --msgbox "No timezones found matching '$filter_input'. Please try a different filter." 6 60
            filter_input="" # Clear filter for next attempt
            continue
        fi

        # Prepare options for dialog_menu
        local menu_options=()
        for tz in "${filtered_timezones[@]}"; do
            menu_options+=( "$tz" "" ) # Each timezone is a key, description is empty
        done

        timezone_selection=$(dialog_menu "Select Timezone" "Choose your desired timezone from the list (or filter again):" "${menu_options[@]}")

        if [ $? -eq 0 ] && [ -n "$timezone_selection" ]; then # User selected a timezone
            echo "$timezone_selection"
            return
        elif [ $? -ne 0 ]; then # User cancelled menu (e.g. pressed Esc)
            echo ""
            return
        fi
        # If user did not select but also didn't cancel the filter, loop for another filter attempt
    done
}

# Function to select the installation drive
select_installation_drive() {
    local drive_options=()
    local drive_selection

    if ! command -v lsblk &> /dev/null; then
        dialog --msgbox "Error: lsblk not found. Cannot list drives." 5 50
        echo ""
        return
    fi

    # Get a list of block devices, excluding loop devices and showing model/size
    # Use awk to correctly separate NAME and the combined SIZE/MODEL as two distinct fields
    local lsblk_output_parsed
    lsblk_output_parsed=$(lsblk -dplno NAME,SIZE,MODEL | grep -v "loop" | awk '{
        device = $1;
        # Reconstruct the description from $2 onwards, handling spaces in model name
        description = "";
        for (i = 2; i <= NF; i++) {
            description = description (i == 2 ? "" : " ") $i;
        }
        print device; # Print device name on one line
        print description; # Print description on the next line
    }')

    # Populate drive_options array with pairs (tag, item)
    # The while loop reads two lines at a time, making them a tag-item pair
    while IFS= read -r tag && IFS= read -r item; do
        drive_options+=( "$tag" "$item" )
    done <<< "$lsblk_output_parsed"

    if [ ${#drive_options[@]} -eq 0 ]; then
        dialog --msgbox "No suitable drives found." 5 50
        echo ""
        return
    fi

    drive_selection=$(dialog_menu "Select Installation Drive" "WARNING: All data on the selected drive will be ERASED.\n\nSelect the drive for Arch Linux installation:" "${drive_options[@]}")

    if [ -n "$drive_selection" ]; then
        echo "$drive_selection"
    else
        echo "" # Return empty if cancelled
    fi
}

# Function to select locales
select_locales() {
    local locale_options=() # This will hold the (tag, item, status) triplets for the dialog
    local locale_selections
    # Pre-selected defaults, en_US.UTF-8 is now explicitly included as requested.
    local default_locales=("en_US.UTF-8" "en_GB.UTF-8" "zh_SG.UTF-8")
    local all_locale_entries=() # To store (clean_id, is_uncommented_status) for all relevant locales
    local filter_input=""
    local current_filtered_indices=() # Indices into all_locale_entries

    if [ ! -f /etc/locale.gen ]; then
        dialog --msgbox "Error: /etc/locale.gen not found. Cannot select locales." 5 60
        echo ""
        return
    fi

    # Read all relevant UTF-8 locales from locale.gen once, processing them
    while IFS= read -r line; do
        # Trim leading/trailing whitespace
        line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

        # Check if the line is a UTF-8 locale entry (commented or uncommented)
        if [[ "$line" =~ ^[^#].*\.UTF-8$ ]] || [[ "$line" =~ ^#.*UTF-8$ ]]; then
            local clean_locale_id=""
            local is_uncommented_orig=false

            if [[ "$line" =~ ^[^#] ]]; then # If it's an uncommented line
                clean_locale_id=$(echo "$line" | awk '{print $1}')
                is_uncommented_orig=true
            else # It's a commented line
                clean_locale_id=$(echo "$line" | sed 's/^#//' | awk '{print $1}')
            fi

            # Ensure we extracted a valid locale ID
            if [ -n "$clean_locale_id" ]; then
                # Store the cleaned ID and whether its original line was uncommented (as "true" or "false")
                all_locale_entries+=( "$clean_locale_id" )
                all_locale_entries+=( "$is_uncommented_orig" ) # Add the boolean flag right after its ID
            fi
        fi
    done < /etc/locale.gen

    if [ ${#all_locale_entries[@]} -eq 0 ]; then
        dialog --msgbox "No suitable UTF-8 locales found in /etc/locale.gen to display." 6 60
        echo ""
        return
    fi

    # Loop for filtering and selection
    while true; do
        filter_input=$(dialog --backtitle "Arch Linux Installation" \
                              --title "Locale Filter" \
                              --inputbox "Enter a filter (e.g., 'en_US', 'de', 'zh_SG') or leave empty for all:\n(Press Enter to apply filter, ESC to cancel locale selection)" \
                              0 0 "$filter_input" \
                              2>&1 >/dev/tty)

        if [ $? -ne 0 ]; then # User cancelled filter input
            echo "" # Return empty selection for locales
            return
        fi

        # Filter the locales based on input
        current_filtered_indices=()
        # Iterate through all_locale_entries by pairs (ID, is_uncommented_status)
        for (( i=0; i<${#all_locale_entries[@]}; i+=2 )); do
            local locale_id="${all_locale_entries[i]}"

            # Case-insensitive filter match
            if [ -z "$filter_input" ] || [[ "${locale_id,,}" =~ "${filter_input,,}" ]]; then
                current_filtered_indices+=( "$i" ) # Store the starting index of the pair
            fi
        done

        if [ ${#current_filtered_indices[@]} -eq 0 ]; then
            dialog --msgbox "No locales found matching '$filter_input'. Please try a different filter." 6 60
            filter_input="" # Clear filter for next attempt
            continue
        fi

        # Build options for dialog --checklist from the filtered list
        locale_options=()
        for idx in "${current_filtered_indices[@]}"; do
            local current_locale_name="${all_locale_entries[idx]}" # This is the clean ID
            local is_uncommented_orig="${all_locale_entries[idx+1]}" # "true" or "false"

            local initial_state="OFF"

            # Set initial state: ON if it was originally uncommented OR if it's in default_locales
            if [ "$is_uncommented_orig" = "true" ]; then
                initial_state="ON"
            else # Check if it's in our specified defaults
                for default_locale in "${default_locales[@]}"; do
                    if [[ "$current_locale_name" == "$default_locale" ]]; then
                        initial_state="ON"
                        break
                    fi
                done
            fi

            # Use the locale name as both tag and item (displayed text)
            locale_options+=( "$current_locale_name" "$current_locale_name" "$initial_state" )
        done

        # Present the filtered list in a checklist
        locale_selections=$(dialog_checklist "Select Locales" "Filtered Locales (matching '$filter_input'):\n\nSelect the locales you want to enable. Press Space to toggle selection:" "${locale_options[@]}")
        local dialog_exit_status=$? # Capture exit status immediately

        if [ "$dialog_exit_status" -eq 0 ]; then # User hit OK on the checklist
            if [ -n "$locale_selections" ]; then
                echo "$locale_selections"
                return # User selected something, return it
            else
                # User hit OK but selected nothing. Ask if they want to re-filter or explicitly quit.
                dialog --yesno "You pressed OK but did not select any locales.\nDo you want to go back and try filtering again?" 0 0
                if [ $? -eq 0 ]; then
                    # User chose Yes, re-filter. Loop continues.
                    # Optionally clear filter_input for a fresh start: filter_input=""
                    continue
                else
                    # User chose No, do not re-filter. Effectively cancelled.
                    echo "" # Return empty as no selection was made and they opted not to re-filter
                    return
                fi
            fi
        else # User cancelled the checklist (e.g. pressed Esc)
            echo "" # Return empty as they cancelled
            return
        fi
    done
}

# Function to select countries for Reflector
select_reflector_countries() {
    local country_options=()
    local country_selections

    # Recommended and common countries (can be expanded)
    # Based on Singapore's location, including nearby and major global mirrors
    local countries=(
        "Singapore"
        "Japan"
        "South_Korea"
        "China"
        "Hong_Kong"
        "Taiwan"
        "Thailand"
        "Indonesia"
        "Malaysia"
        "Vietnam"
        "Australia"
        "India"
        "United_States"
        "Germany"
        "Netherlands"
        "" # Separator - this will be skipped by the loop
        "United_Kingdom"
        "Canada"
        "France"
        "Brazil"
    )

    local default_selected=("Australia")

    for country in "${countries[@]}"; do
        if [ -z "$country" ]; then continue; fi # Skip empty lines/separators
        local default_state="OFF"
        for def_country in "${default_selected[@]}"; do
            if [[ "$country" == "$def_country" ]]; then
                default_state="ON"
                break
            fi
        done
        country_options+=( "$country" "" "$default_state" )
    done

    country_selections=$(dialog_checklist "Reflector Countries" "Select countries for your Pacman mirrors (for optimal speed, choose nearby locations):\n\n(Press Space to toggle selection)" "${country_options[@]}")

    if [ -n "$country_selections" ]; then
        # Reflector expects space-separated list. We should ensure this.
        # dialog output is already space-separated for checklist
        echo "$country_selections"
    else
        echo "" # Return empty if cancelled
    fi
}

# Function to select keyboard layout
select_keyboard_layout() {
    local keyboard_layout_selection
    local filter_input=""
    local filtered_keymaps=()
    local keymap_list_raw

    if ! command -v localectl &> /dev/null; then
        dialog --msgbox "Error: localectl not found. Cannot list keyboard layouts." 5 60
        echo "us" # Fallback to 'us' if localectl is not available
        return
    fi

    keymap_list_raw=$(localectl list-keymaps)

    # Initial default selection
    local initial_default_keymap="us"
    local initial_selection_prompt="Enter a filter (e.g., 'us', 'de', 'fr', 'dvorak') or leave empty for all.\nIf no layout is selected, '$initial_default_keymap' will be used.\n(Press Enter to apply filter, ESC to cancel keyboard layout selection)"

    while true; do
        filter_input=$(dialog --backtitle "Arch Linux Installation" \
                              --title "Keyboard Layout Filter" \
                              --inputbox "$initial_selection_prompt" \
                              0 0 "$filter_input" \
                              2>&1 >/dev/tty)

        if [ $? -ne 0 ]; then # User cancelled filter input
            dialog --yesno "Keyboard layout selection cancelled. The default '$initial_default_keymap' will be used.\nDo you want to re-attempt selection?" 0 0
            if [ $? -eq 0 ]; then
                continue # User chose to re-attempt
            else
                echo "$initial_default_keymap" # User chose not to re-attempt, use default
                return
            fi
        fi

        # Filter the keymaps based on input (case-insensitive)
        if [ -n "$filter_input" ]; then
            mapfile -t filtered_keymaps < <(echo "$keymap_list_raw" | grep -i "$filter_input")
        else
            mapfile -t filtered_keymaps < <(echo "$keymap_list_raw")
        fi

        if [ ${#filtered_keymaps[@]} -eq 0 ]; then
            dialog --msgbox "No keyboard layouts found matching '$filter_input'. Please try a different filter." 6 70
            filter_input="" # Clear filter for next attempt
            continue
        fi

        # Build options for dialog --menu
        local menu_options=()
        for keymap in "${filtered_keymaps[@]}"; do
            menu_options+=( "$keymap" "" ) # Tag and Item are the same, description is empty
        done

        # Present the filtered list in a menu
        keyboard_layout_selection=$(dialog_menu "Select Keyboard Layout" "Filtered Layouts (matching '$filter_input'):\n\nSelect your desired keyboard layout (e.g., 'us', 'de', 'fr')." "${menu_options[@]}")
        local dialog_exit_status=$?

        if [ "$dialog_exit_status" -eq 0 ]; then # User hit OK on the menu
            if [ -n "$keyboard_layout_selection" ]; then
                echo "$keyboard_layout_selection"
                return # User selected something, return it
            else
                # This case might occur if dialog --menu has only one item and user hits OK
                # without explicitly selecting it, or if something unexpected happens.
                dialog --yesno "You pressed OK but did not select any keyboard layout. The default '$initial_default_keymap' will be used.\nDo you want to go back and select one?" 0 0
                if [ $? -eq 0 ]; then
                    continue # User chose to re-attempt selection
                else
                    echo "$initial_default_keymap" # User chose not to re-attempt, use default
                    return
                fi
            fi
        else # User cancelled the menu (e.g. pressed Esc)
            dialog --yesno "Keyboard layout selection cancelled. The default '$initial_default_keymap' will be used.\nDo you want to re-attempt selection?" 0 0
            if [ $? -eq 0 ]; then
                continue # User chose to re-attempt selection
            else
                echo "$initial_default_keymap" # User chose not to re-attempt, use default
                return
            fi
        fi
    done
}


# --- Main installation script flow example ---

# Ensure dialog, util-linux, pciutils are installed (essential for detection and dialog menus)
# In a real Arch install script, you'd typically run this early:
# pacman -S dialog util-linux pciutils --noconfirm

echo "--- Arch Linux Installation Setup ---"
echo "Starting hardware and system configuration selection..."

# Call the functions to get user selections
selected_cpu_driver=$(get_cpu_drivers)
selected_gpu_driver=$(get_gpu_drivers)
selected_virtualizer_driver=$(get_virtualizer_drivers)
selected_timezone=$(select_timezone)
selected_drive=$(select_installation_drive)
selected_locales=$(select_locales)
selected_reflector_countries=$(select_reflector_countries)
selected_keyboard_layout=$(select_keyboard_layout)


# Display selections (for testing purposes)
echo -e "\n--- Your Selections ---"
echo "Selected CPU Driver: $selected_cpu_driver"
echo "Selected GPU Driver: $selected_gpu_driver"
echo "Selected Virtualizer Driver: $selected_virtualizer_driver"
echo "Selected Timezone: $selected_timezone"
echo "Selected Installation Drive: $selected_drive"
echo "Selected Locales: $selected_locales"
echo "Selected Reflector Countries: $selected_reflector_countries"
echo "Selected Keyboard Layout: $selected_keyboard_layout"

echo -e "\n--- End of Selections ---"

echo -e "\nScript finished. Use the printed selections for your Arch Linux installation."

# --- Integration into your actual Arch Linux installation steps ---
# This is where you would use these variables. Examples:

# 1. For Drive Selection:
# if [ -n "$selected_drive" ]; then
#     dialog --yesno "Are you sure you want to format $selected_drive? This will erase all data!" 0 0
#     if [ $? -eq 0 ]; then
#         # Implement partitioning and formatting here
#         # Example: parted -s "$selected_drive" mklabel gpt
#         #          parted -s "$selected_drive" mkpart primary fat32 1MiB 513MiB
#         #          parted -s "$selected_drive" set 1 esp on
#         #          parted -s "$selected_drive" mkpart primary ext4 513MiB 100%
#         #          mkfs.fat -F32 "${selected_drive}1"
#         #          mkfs.ext4 "${selected_drive}2"
#         #          mount "${selected_drive}2" /mnt
#         #          mkdir -p /mnt/boot/efi
#         #          mount "${selected_drive}1" /mnt/boot/efi
#         echo "Drive $selected_drive selected and would be formatted/partitioned."
#     else
#         echo "Drive formatting cancelled. Exiting."
#         exit 1
#     fi
# fi

# 2. For Pacstrap:
# Example pacstrap command
# pacstrap /mnt base linux linux-firmware "$selected_cpu_driver" "$selected_gpu_driver" "$selected_virtualizer_driver"

# 3. For Timezone:
# After chrooting:
# arch-chroot /mnt ln -sf "/usr/share/zoneinfo/$selected_timezone" /etc/localtime
# arch-chroot /mnt hwclock --systohc

# 4. For Locales:
# After chrooting:
# for locale_code in $selected_locales; do
#     sed -i "/^#$locale_code/s/^#//" /etc/locale.gen
# done
# arch-chroot /mnt locale-gen
# For LANG environment variable (e.g., set to the first selected locale):
# echo "LANG=${selected_locales%% *}" > /etc/locale.conf # Uses the first selected locale
# export LANG="${selected_locales%% *}" # For current shell session in chroot

# 5. For Reflector:
# Requires reflector package to be installed first (e.g., via pacstrap)
# After chrooting (or after pacstrap if reflector is installed directly):
# if [ -n "$selected_reflector_countries" ]; then
#    # Convert space-separated list of countries into --country arguments
#    reflector_country_args=""
#    for country in $selected_reflector_countries; do
#        reflector_country_args+="--country \"$country\" "
#    done
#    # Example:
#    # arch-chroot /mnt reflector --latest 5 --protocol https --sort rate $reflector_country_args --save /etc/pacman.d/mirrorlist
#    echo "Reflector command would be: reflector --latest 5 --protocol https --sort rate $reflector_country_args --save /etc/pacman.d/mirrorlist"
# fi
