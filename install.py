#----------------------------------------------------------------------------------------------------------------------
# Arch Linux installation
#
# Bootable USB:
# - [Download](https://archlinux.org/download/) ISO and GPG files
# - Verify the ISO file: `$ pacman-key -v archlinux-<version>-dual.iso.sig`
# - Create a bootable USB with: `# dd if=archlinux*.iso of=/dev/sdX && sync`
#
# UEFI setup:
# - Set boot mode to UEFI, disable Legacy mode entirely (checked)
# - Delete preloaded OEM keys for Secure Boot, allow custom ones.
# - Temporarily disable Secure Boot.
# - Make sure a strong UEFI administrator password is set.
# - Set SATA operation to AHCI mode.
#
# Drive layout:
#    /dev/sdx
#            /sdx1            - primary    -  15 GB >
#                 /archlinux  - encrypted
#            /sdx2            - esp        - 550 MB
#
# Run installation:
#
# - Connect to wifi via: `# iwctl station wlan0 connect WIFI-NETWORK`
# - Run:
#   pacman -Sy
#   pacman -S git python-rich
#   git clone https://github.com/echjansen/pure-arch
#   cd pure-arch
#   python secure_arch.py
#----------------------------------------------------------------------------------------------------------------------
# Todos:
# - [X] Use 'dialog' for the user input
# - [X] arch-chroot /mnt chpasswd --> FAILS | chpasswd: (line 1, user $USER_NAME) password not changed
# - [X] Remove old CommandExecutor
# - [ ] Use Luks 2 for encryption
# - [ ] copy_file_structure uses old logging style
#       INFO     Copying file from rootfs to /mnt
#       INFO:rich:[yellow]Copying file from rootfs to /mnt[/yellow]
# - [ ] Read a config file instead of queering user entry
# - [ ] Create variable substitution in the same fashion across functions
# - [ ] Switch monitor on the fly until correct, then move on
# - [ ] Hide initial system tests that - correctly - could fail
#----------------------------------------------------------------------------------------------------------------------
import os
import sys
import shutil
import logging
import subprocess
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from rich.theme import Theme
from rich.prompt import Prompt
from rich.rule import Rule
from rich.logging import RichHandler
from typing import Union

# Debugging variables
DEBUG = True                   # If True, report on command during execution
STEP = False                   # If true, step one command at the time

# Global Constants
SYSTEM_FONT = 'ter-132n'       # System font ('ter-132n' , 'ter-716n')
PART_1_NAME = "PRIMARY"
PART_2_NAME = "ESP"
PART_1_UUID = 'archlinux'      # Name of volume 1 (archlinux)
PART_2_UUID = 'esp'            # Name of volume 2 (esp)
SYSTEM_LOG_FILE ='install.log' # Set to None to disable or with a string "install.log"
BTRFS_MOUNT_OPT = "defaults,noatime,nodiratime,compress=zstd,space_cache=v2"

# Global Variables
DRIVE = None                    # The device that will be made into a backup device
DRIVE_PASSWORD = None           # Encryption password for partitions
USER_NAME = None                # User name for backup devices (no root)
USER_PASSWORD = None            # User password for backup device
LUKS_PASSWORD = None            # Luks password for drive(s)
SYSTEM_HOSTNAME = None          # System hostname
SYSTEM_LOCALE = None            # System locale ('en_US')
SYSTEM_KEYB = None              # System keyboard layout
SYSTEM_COUNTRY = None           # System country ('Australia')
SYSTEM_TIMEZONE = None          # System timezone, used for repository downloads
SYSTEM_CPU = None               # System CPU brand (Intel, AMD, etc)
SYSTEM_GPU = None               # System GPU brand (Intel, AMD, NVIDIA, etc)
SYSTEM_GPU_INT = None           # System GPU is integrated in CPU
SYSTEM_VIRT = None              # System virtualizer (if any) (oracle, vmware, docker, etc)
SYSTEM_PKGS = None              # System packages to install
SYSTEM_CMD = None               # System commands lines
SYSTEM_MODULES = None           # System modules for mkinitcpio
SYSTEM_WIPE_DISK = None         # Wipe entire disk before formatting (lengthy)

# Configure me or leave commented out
# DRIVE = '/dev/sdb'              # The device that will be made into a backup device
# DRIVE_PASSWORD = '123'          # Encryption password for partitions
# USER_NAME = 'echjansen'         # User name for backup devices (no root)
# USER_PASSWORD = '123'           # User password for backup device
# LUKS_PASSWORD = '123'           # Luks password for drive(s)
# SYSTEM_HOSTNAME = 'archlinux'   # System host name
# SYSTEM_LOCALE = 'en_US'         # System locale ('en_US')
SYSTEM_COUNTRY = 'Australia'    # System country ('Australia')
# SYSTEM_KEYB = 'us'              # System keyboard layout ('us')
# SYSTEM_TIMEZONE  = 'Australia/Melbourne'   # System timezone

# 'rich' objects
theme = Theme({
    'info':     'yellow',
    'warning':  'bold yellow',
    'success':  'green',
    'error':    'red',
    'critical': 'bold reverse red',
    'debug':    'blue',
})

class CustomFormatter(logging.Formatter):
    COLORS = {
        'INFO':      'yellow',
        'WARNING':   'bold yellow',
        'success':   'green',
        'ERROR':     'red',
        'DEBUG':     'blue',
        'CRITICAL':  'bold reverse red',
        }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, 'white')
        record.msg = f'[{log_color}]{record.msg}[/{log_color}]'
        return super().format(record)

#----------------------------------------------------------------------------------------------------------------------
# System Check and Support Functions
#----------------------------------------------------------------------------------------------------------------------
def check_sudo():
    """
    Check that the software is running with sudo privileges.
    """

    if os.getegid() == 0:
        log.info("Script is running with sudo privileges.")
        return True
    else:
        log.critical("Application must run with sudo privileges.")
        return False

def check_uefi():
    """
    Check that the system is running in UEFI mode (Unified Extensible Firmware Interface).
    """

    if os.path.exists('/sys/firmware/efi/'):
        log.info("System is booted in UEFI mode.")
        return True
    else:
        log.critical("System is NOT booted in UEFI mode (likely BIOS/Legacy mode).")
        return False

def check_secure_boot():
    """
    Check that the system is running with Secure Boot
    """

    try:
        # Execute dmesg | grep -1 tpm
        result = subprocess.run(
            ['dmesg'],
            capture_output=True,
            text=True,
            check=True          # Check for non-zero exit code
        )
        dmesg_output = result.stdout.strip()

        grep_result = subprocess.run(
            ['grep', '-i', 'tpm'],
            input=dmesg_output,
            capture_output=True,
            text=True,
            check=False          # Do Not check for non-zero exit code
        )
        grep_output = grep_result.stdout.strip()

        if grep_output:
            log.info('TPM (Trusted Platform Module) detected.')
            return True
        else:
            log.critical('TPM (Trusted Platform Module) not detected.')
            return False

    except subprocess.CalledProcessError as e:
        console.print(f'Error executing dmesg: {e}', style='critical')
        exit()
    except Exception as e:
        console.print(f'An unexpected error occurred: {e}', style='critical')
        exit()

def get_cpu_brand() -> str:
    """
    Uses the 'lscpu' command to determine the CPU brand (Intel, AMD, etc.).

    Returns:
        str: The CPU brand name.
             Returns "Unknown" if the brand cannot be determined or an error occurs.
    """
    try:
        # Execute lscpu
        result = subprocess.run(
            ['lscpu'],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()

        # Search for the "CPU vendor" line
        vendor_id = None
        model_name = None
        for line in output.splitlines():
            if "Vendor ID:" in line:
                vendor_id = line.split(":", 1)[1].strip()
            if "Model name:" in line:
                model_name = line.split(":", 1)[1].strip()

        if vendor_id:
            if vendor_id == "GenuineIntel":
                return "Intel"
            elif vendor_id == "AuthenticAMD":
                return "AMD"
            else:
                if model_name:
                   return model_name # Returning the "Model name"
                else:
                   return vendor_id  # Return the raw "CPU vendor" string if known brands aren't matched.
        else:
            console.print("Could not determine CPU brand from lscpu output.", style='error')
            return "Unknown"

    except subprocess.CalledProcessError as e:
        console.print(f"Error executing lscpu: {e}", style='critical')
        return "Unknown"
    except FileNotFoundError:
        console.print("Error: lscpu command not found. Please ensure lscpu is installed.", style='critical')
        return "Unknown"
    except Exception as e:
        console.print(f"An unexpected error occurred: {e}", style='critical')
        return "Unknown"

def get_graphics_card_brand() -> str:
    """
    Uses the 'lspci' command to determine the graphics card brand (Intel, NVIDIA, AMD, etc.).

    Returns:
        str: The graphics card brand name.
             Returns "Unknown" if the brand cannot be determined or an error occurs.
    """

    try:
        # Execute lspci to get VGA compatible controller information
        result = subprocess.run(
            ['lspci', '-vnn', '-d', '::0300'],  # Filter for VGA compatible controllers
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()

        # Parse the output to find the graphics card brand
        for line in output.splitlines():
            if "VGA compatible controller" in line:
                # Extract the brand name from the line
                brand = line.split("VGA compatible controller")[1].strip()

                # Normalize the brand (remove extra info, use common names)
                if "Intel" in brand:
                    return "Intel"
                elif "NVIDIA" in brand:
                    return "NVIDIA"
                elif "AMD" in brand or "ATI" in brand:
                    return "AMD"  # Using AMD as the standard name
                elif "VMware" in brand :
                    return "VMWare"  # VMWare Virtualisation
                elif "Oracle" in brand :
                    return "VirtualBox"  # VirtualBox Virtualisation
                else:
                    return brand  # Return the raw brand if known brands aren't matched.

        console.print("Could not determine graphics card brand from lspci output.", style='error')
        return "Unknown"

    except subprocess.CalledProcessError as e:
        console.print(f"Error executing lspci: {e}", style='critical')
        return "Unknown"
    except FileNotFoundError:
        console.print("Error: lspci command not found. Please ensure lspci is installed.", style='critical')
        return "Unknown"
    except Exception as e:
        console.print(f"An unexpected error occurred: {e}", style='critical')
        return "Unknown"

def get_virtualizer() -> str:
    """
    Uses the 'systemd-detect-virt' command to determine the current virtualizer.

    Returns:
        str: The name of the virtualizer (e.g., "vmware", "kvm", "docker", "lxc").
             Returns "none" if running on bare metal or the virtualizer cannot be determined.
             Returns "Unknown" if an error occurs.
    """

    try:
        # Execute systemd-detect-virt
        result = subprocess.run(
            ['systemd-detect-virt'],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()

        if output:
            return output
        else:
            return "metal"  # Running on bare metal

    except subprocess.CalledProcessError as e:
        console.print(f"Error executing systemd-detect-virt: {e}", style='critical')
        return "Unknown"
    except FileNotFoundError:
        console.print("Error: systemd-detect-virt command not found. Please ensure systemd is installed.", style='critical')
        return "Unknown"
    except Exception as e:
        console.print(f"An unexpected error occurred: {e}", style='critical')
        return "Unknown"


def get_packages_from_file(filepath: str) -> List[str]:
    """
    Reads a file containing a list of package names (one per line),
    removes comments, and returns a list of clean package names.

    Comments start with '#' and can be the entire line or behind the package name.

    To use with for instance pacstrap use ' '.join(packages)

    Args:
        filepath: The path to the file containing the package list.

    Returns:
        A list of package names (without comments).
    """
    packages: List[str] = []

    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()  # Remove leading/trailing whitespace

                # Skip empty lines and comment-only lines
                if not line or line.startswith('#'):
                    continue

                # Remove comments at the end of the line
                if '#' in line:
                    line = line.split('#', 1)[0].strip() # Splitting from the left side only once

                # Add the package name to the list
                if line:  # Ensure there's something left after removing comments
                    packages.append(line)

    except FileNotFoundError:
        console.print(f"Error: File not found: {filepath}", style='critical')
    except Exception as e:
        console.print(f"An error occurred: {e}", style='critical')

    return packages

def find_subdirectory(source_name: str) -> Union[str, None]:
    """
    Finds the source directory by name within the current directory structure
    using the 'find' command.

    Args:
        source_name: The name of the source directory to find.

    Returns:
        The absolute path to the source directory if found, otherwise None.
    """

    try:
        # Execute the 'find' command
        result = subprocess.run(
            ['find', '.', '-name', source_name, '-type', 'd', '-print0'],  # Find directories only, print null-terminated
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()

        if output:
            # Split the output by null characters (handles filenames with spaces or newlines)
            paths = output.split('\0')
            # Return the first matching directory (assuming there's only one)
            return os.path.abspath(paths[0])

        else:
            console.print(f"Error: Source directory '{source_name}' not found using 'find' command.", style='error')
            return None

    except subprocess.CalledProcessError as e:
        console.print(f"Error executing find command: {e}", style='critical')
        return None
    except FileNotFoundError:
        console.print("Error: find command not found. Please ensure find is installed.", style='critical')
        return None
    except Exception as e:
        console.print(f"An unexpected error occurred: {e}", style='critical')
        return None

def copy_file_structure(source: str, destination: str) -> None:
    """
    Copies the file structure (folders and files) from a source directory to a
    destination directory, creating any missing folders in the destination.

    Args:
        source: The path to the source directory.
        destination: The path to the destination directory.
    """
    log.info(f'Copying file from {source} to {destination}')

    try:
        # Check if the source directory exists
        if not os.path.isdir(source):
            source = find_subdirectory(source)
            if not source:
                log.error(f"Error: Source directory '{source}' not found.", style='error')
                return

        # Create the destination directory if it doesn't exist
        os.makedirs(destination, exist_ok=True)  # exist_ok=True prevents an error if the directory already exists

        for root, _, files in os.walk(source):
            # Create the corresponding directory structure in the destination
            dest_dir = os.path.join(destination, os.path.relpath(root, source))
            os.makedirs(dest_dir, exist_ok=True)

            for file in files:
                source_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                try:
                    shutil.copy2(source_file, dest_file)  # copy2 preserves metadata
                except Exception as e:
                    log.error(f"Warning: Could not copy '{source_file}' to '{dest_file}': {e}")

    except Exception as e:
        log.exception('An unexpected error occurred')
        return -1, "", str(e)

#----------------------------------------------------------------------------------------------------------------------
# User Entry class - using 'dialog' package (installed in this script)
#----------------------------------------------------------------------------------------------------------------------
class UserEntry:
    """A class for gathering user information via dialog prompts."""

    def __init__(self):
        """Initializes the UserEntry class."""
        self.user_data = {}  # To store user entries

    # --- Support Functions ---

    def _run_dialog(self, *args):
        """Run dialog with fixed dimensions and force compatibility with terminal emulators."""
        cmd = ['dialog',  '--clear', '--stdout'] + list(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            os.system('clear')  # Helps clean up after dialog in terminal emulator
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Dialog command failed with return code {e.returncode}: {e.stderr}")
            return None  # Treat non-zero return as cancel
        except FileNotFoundError:
            print("Error: 'dialog' program not found.  Please install it.")
            sys.exit(1)
        except Exception as e:
            print(f"Error running dialog: {e}")
            return None

    def _run_inputbox(self, title, text, init="", height=0, width=0):
        """Runs an inputbox dialog prompt using the 'dialog' program."""
        cmd = ["--title", title, "--inputbox", text, str(height), str(width), init]
        result = self._run_dialog(*cmd)
        return result

    def _run_passwordbox(self, title, text, height=0, width=0):
        """Runs a passwordbox dialog prompt using the 'dialog' program."""
        cmd = ["--title", title, "--passwordbox", text, str(height), str(width)]
        result = self._run_dialog(*cmd)
        return result

    def run_yesno(self, title, text, height=0, width=0):
        """Runs a yes/no dialog prompt using the 'dialog' program.

        Returns:
            True if 'Yes' is selected.
            False if 'No' or Cancel is selected, or if an error occurs.
        """
        cmd = ['dialog', '--title', title, '--yesno', text, str(height), str(width)]
        try:
            # Clear the screen using escape codes
            print("\033[2J\033[H", end="")  # Clear screen and move cursor to top-left
            result = subprocess.run(cmd, capture_output=False, text=True, check=False)
            return result.returncode == 0
        except FileNotFoundError:
            print("Error: 'dialog' program not found.  Please install it.")
            sys.exit(1)
        except Exception as e:
            print(f"Error running dialog: {e}")
            return False

    def _run_msgbox(self, title, text, height=0, width=0):
        """Runs a message box dialog prompt using the 'dialog' program."""
        cmd = ["--title", title, "--msgbox", text, str(height), str(width)]
        self._run_dialog(*cmd)  # No return value needed for msgbox

    # --- System Functions ---

    def _get_drive_info(self, drive):
        """Gets drive size and model information using `lsblk` and `hdparm`."""
        size = "Unknown"
        model = "Unknown"

        try:
            # Get size using lsblk
            result = subprocess.run(['lsblk', '-dn', '-b', '-o', 'SIZE', f'/dev/{drive}'], capture_output=True, text=True, check=True)
            size_bytes = int(result.stdout.strip())
            size_gb = size_bytes / (1024 ** 3)  # Convert to GB
            size = f"{size_gb:.2f} GB"
        except subprocess.CalledProcessError as e:
            print(f"Error getting size for {drive}: {e.stderr}")
        except Exception as e:
            print(f"Error getting size for {drive}: {e}")

        try:
            # Get model using hdparm
            result = subprocess.run(['hdparm', '-I', f'/dev/{drive}'], capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                if "Model Number:" in line:
                    model = line.split(":", 1)[1].strip()
                    break
        except subprocess.CalledProcessError as e:
            print(f"Error getting model for {drive}: {e.stderr}")
        except FileNotFoundError:
            print("Error: hdparm not found. Please install it.")
        except Exception as e:
            print(f"Error getting model for {drive}: {e}")

        return size, model

    def _get_drives(self):
        """Lists available drives and their info."""
        try:
            result = subprocess.run(['lsblk', '-dn', '-o', 'NAME'], capture_output=True, text=True, check=True)
            drives = [line.strip() for line in result.stdout.splitlines() if "loop" not in line]
            drive_info = []
            for drive in drives:
                size, model = self._get_drive_info(drive)
                drive_info.append((drive, size, model))
            return drive_info
        except subprocess.CalledProcessError as e:
            print(f"Error listing drives: {e.stderr}")
            return []
        except FileNotFoundError:
            print("Error: 'lsblk' command not found.")
            return []
        except Exception as e:
            print(f"An error occurred listing drives: {e}")
            return []

    def _get_timezones(self):
        """Lists timezones from /usr/share/zoneinfo using glob."""
        timezone_dir = "/usr/share/zoneinfo"
        timezones = []
        for root, _, files in os.walk(timezone_dir):
            for file in files:
                full_path = os.path.join(root, file)
                if os.path.isfile(full_path):  # Only add files, skip directories that may not be valid timezones
                    relative_path = os.path.relpath(full_path, timezone_dir)
                    timezones.append(relative_path)  # Relative to /usr/share/zoneinfo
        return timezones

    def _get_locales(self):
        """Reads available locales from /usr/share/i18n/SUPPORTED."""
        try:
            with open("/usr/share/i18n/SUPPORTED", "r") as f:
                locales = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                return locales
        except FileNotFoundError:
            print("Error: /usr/share/i18n/SUPPORTED not found.")
            return []
        except Exception as e:
            print(f"Error reading locales: {e}")
            return []

    def _get_keyboard_layouts(self, keymap_dir="/usr/share/kbd/keymaps"):
        """Lists available keyboard layouts from the specified directory."""
        layouts = []
        try:
            for root, _, files in os.walk(keymap_dir):
                for file in files:
                    if file.endswith(".map.gz") or file.endswith(".map"):
                        # Remove the .map.gz or .map extension to get the layout name
                        layout_name = file[:-7] if file.endswith(".map.gz") else file[:-4]
                        layouts.append(layout_name)
        except Exception as e:
            print(f"Error reading keyboard layouts: {e}")
            return []
        return sorted(layouts)  # Sort the layouts alphabetically

    def _get_reflector_countries(self):
        """Gets the list of countries from `reflector --list-countries`."""
        try:
            result = subprocess.run(['reflector', '--list-countries'], capture_output=True, text=True, check=True)
            countries = [line.strip() for line in result.stdout.splitlines()]
            return countries
        except FileNotFoundError:
            print("Error: reflector not found. Please install it.")
            return []
        except subprocess.CalledProcessError as e:
            print(f"Error listing countries: {e.stderr}")
            return []
        except Exception as e:
            print(f"An error occurred listing countries: {e}")
            return []

    def _set_console_font(self, font):
        """Sets the console font using `setfont`."""
        try:
            subprocess.run(['setfont', font], check=True)
            print(f"Console font set to: {font}")
        except FileNotFoundError:
            print("Error: setfont not found. Please install it.")
        except subprocess.CalledProcessError as e:
            print(f"Error setting font: {e.stderr}")

    # --- User Selection Functions ---

    def configure_hostname(self, default=""):
        """Prompts the user for a hostname."""
        result = self._run_inputbox("Hostname Configuration", "Enter the desired hostname:", default, height=8, width=40)
        if result:
            self.user_data["hostname"] = result
        return result

    def configure_username(self):
        """Prompts the user for a User name."""
        result = self._run_inputbox("User Configuration", "Enter the username:", height=8, width=40)
        if result:
            self.user_data["username"] = result
        return result

    def configure_userpassword(self):
        """Prompts the user for a User password (with confirmation)."""
        while True:
            password = self._run_passwordbox("User Configuration", "Enter the user password:", height=8, width=40)
            if not password:
                return None

            password_confirm = self._run_passwordbox("User Configuration", "Confirm the user password:", height=8, width=40)
            if not password_confirm:
                return None

            if password == password_confirm:
                self.user_data["userpassword"] = password
                return password
            else:
                print("Passwords do not match. Please try again.")

    def configure_lukspassword(self):
        """Prompts the user for a Luks password (with confirmation)."""
        while True:
            password = self._run_passwordbox("Luks Configuration", "Enter the Luks password:", height=8, width=40)
            if not password:
                return None

            password_confirm = self._run_passwordbox("Luks Configuration", "Confirm the Luks password:", height=8, width=40)
            if not password_confirm:
                return None

            if password == password_confirm:
                self.user_data["lukspassword"] = password
                return password
            else:
                print("Passwords do not match. Please try again.")


    def configure_drive(self):
        """Presents a menu to select a drive for installation."""
        drives = self._get_drives()
        if not drives:
            print("No drives found. Please ensure you have a drive connected.")
            return None

        drive_items = []
        for drive, size, model in drives:
            label = f"{drive} - {model} ({size})"
            drive_items.append((drive, label))

        menu_items = []
        for drive, label in drive_items:
            menu_items.extend([drive, label])

        selected_drive = self._run_dialog("--menu", "Select the drive for installation:", "20", "70", "10", *menu_items)

        if selected_drive:
            selected_drive = "/dev/" + selected_drive
            self.user_data["drive"] = selected_drive
        return selected_drive

    def configure_locale(self, default=""):
        """Prompts the user for a locale and filters the results."""
        locales = self._get_locales()
        if not locales:
            print("No locales found.")
            return None

        while True:
            filter_string = self._run_inputbox("Locale Selection", "Enter a filter string (e.g., 'en_US') or leave blank for all:", default, height=8, width=60)
            if filter_string is None:
                return None

            filtered_locales = [locale for locale in locales if filter_string.lower() in locale.lower()]

            if not filtered_locales:
                print("No locales match the filter. Try again.")
            else:
                locale_items = [(locale, locale) for locale in filtered_locales]
                menu_items = []
                for locale, label in locale_items:
                    menu_items.extend([locale, label])

                selected_locale = self._run_dialog("--menu", "Select the desired locale:", "15", "60", "10", *menu_items)
                if selected_locale:
                    self.user_data["locale"] = selected_locale
                    return selected_locale
                else:
                    return None  # User canceled the locale selection

    def configure_timezone(self):
        """Prompts the user for a timezone and filters the results."""
        timezones = self._get_timezones()
        if not timezones:
            print("No timezones found.")
            return None

        while True:
            filter_string = self._run_inputbox("Timezone Selection", "Enter a filter string (e.g., 'America') or leave blank for all:", height=8, width=60)
            if filter_string is None:
                return None

            filtered_timezones = [tz for tz in timezones if filter_string.lower() in tz.lower()]

            if not filtered_timezones:
                print("No timezones match the filter. Try again.")
            else:
                timezone_items = [(tz, tz) for tz in filtered_timezones]

                menu_items = []
                for tz, label in timezone_items:
                    menu_items.extend([tz, label])

                selected_timezone = self._run_dialog("--menu", "Select the desired timezone:", "15", "60", "10", *menu_items)
                if selected_timezone:
                    self.user_data["timezone"] = selected_timezone
                    return selected_timezone
                else:
                    return None  # User canceled the timezone selection

    def configure_keyboard(self):
        """Presents a menu to select a keyboard layout."""
        keyboard_layouts = self._get_keyboard_layouts()
        if not keyboard_layouts:
            print("No keyboard layouts found.")
            return None

        layout_items = [(layout, layout) for layout in keyboard_layouts]

        menu_items = []
        for layout, label in layout_items:
            menu_items.extend([layout, label])

        selected_keyboard = self._run_dialog("--menu", "Select the desired keyboard layout (us):", "20", "60", "10", *menu_items)  # Adjusted sizes
        if selected_keyboard:
            self.user_data["keyboard"] = selected_keyboard
        return selected_keyboard

    def configure_country_reflector(self):
        """Presents a menu to select a country from the reflector country list."""
        countries = self._get_reflector_countries()
        if not countries:
            print("No countries found.")
            return None

        country_items = [(country, country) for country in countries]

        menu_items = []
        for country, label in country_items:
            menu_items.extend([country, label])

        selected_country = self._run_dialog("--menu", "Select a country:", "20", "60", "10", *menu_items)
        if selected_country:
            self.user_data["country"] = selected_country
        return selected_country

    def configure_country(self):
        """Presents a menu to select a country from a static list."""
        countries = [  # A reasonably comprehensive list
            "United States", "Canada", "United Kingdom", "Germany", "France", "Japan", "China", "India",
            "Australia", "Brazil", "Mexico", "Italy", "Spain", "Netherlands", "Switzerland", "Sweden",
            "Belgium", "Austria", "Norway", "Denmark", "Finland", "Ireland", "Portugal", "Greece",
            "Poland", "Russia", "South Africa", "Argentina", "Chile", "Colombia", "Peru", "Venezuela",
            "Singapore", "Hong Kong", "South Korea", "Taiwan", "Thailand", "Vietnam", "Indonesia",
            "Malaysia", "Philippines", "New Zealand"
        ]

        sorted_countries = sorted(countries)

        country_items = [(country, country) for country in sorted_countries]

        menu_items = []
        for country, label in country_items:
            menu_items.extend([country, label])

        selected_country = self._run_dialog("--menu", "Select a country:", "20", "60", "10", *menu_items)
        if selected_country:
            self.user_data["country"] = selected_country
        return selected_country

    def configure_font(self):
        """Presents a menu to select a console font and applies it immediately."""
        font_options = [
            ("ter-116n", "Small"),
            ("ter-124n", "Medium"),
            ("ter-128n", "Large"),
            ("ter-132n", "Extra Large")  # Common Terminus fonts
        ]

        while True:  # Loop until the user is satisfied and presses OK
            menu_items = []
            for font, label in font_options:
                menu_items.extend([font, label])

            # The following code is modified to use --radiolist rather than --menu, and add a --ok-label argument
            selected_font = self._run_dialog("--radiolist", "Select a console font:", "20", "60", "10", "OK", "Cancel", "on", *menu_items)

            if selected_font:
                self._set_console_font(selected_font)  # Apply the selected font immediately
                self.user_data["font"] = selected_font
                break  # Exit the loop if a font is selected
            else:
                # The user canceled the font selection.
                return None

        return selected_font

    def configure(self):
        """Main function to orchestrate the Arch Linux configuration process."""
        print("Starting Arch Linux Configuration...")

        # First, configure the font size
        font = self.configure_font()
        if font:
            self._set_console_font(font)
        else:
            print("Font configuration canceled or failed. Using default font.")

        drive = self.configure_drive()
        if not drive:
            print("Drive selection canceled.")
            return None

        lukspassword = self.configure_lukspassword()
        if not lukspassword:
            print("Password configuration canceled.")
            return None

        hostname = self.configure_hostname("archlinux")
        if not hostname:
            print("Hostname configuration canceled.")
            return None

        username = self.configure_username()
        if not username:
            print("User configuration canceled.")
            return None

        userpassword = self.configure_userpassword()
        if not userpassword:
            print("Password configuration canceled.")
            return None

        locale = self.configure_locale("en_US")
        if not locale:
            print("Locale selection canceled.")
            return None

        timezone = self.configure_timezone()
        if not timezone:
            print("Timezone configuration canceled.")
            return None

        keyboard = self.configure_keyboard()
        if not keyboard:
            print("Keyboard layout selection canceled.")
            return None

        country = self.configure_country()
        if not country:
            print("Country selection canceled.")
            return None

        # --- Configuration Summary ---
        summary_text = f"""
        Hostname: ......... {hostname}
        Username: ......... {username}
        Drive: ............ {drive}
        Locale: ........... {locale}
        Timezone: ......... {timezone}
        Keyboard Layout: .. {keyboard}
        Country: .......... {country}
        """

        self._run_msgbox("Configuration Summary", summary_text, 20, 60)

        confirmation_text = f"""
        WARNING! You are about to delete all data on drive {drive}!!!

        Do you want to continue with the installation?
        """
        confirm = self.run_yesno("Confirmation", confirmation_text)
        if not confirm:
            print("Installation canceled.")
            return None

        return self.user_data

#----------------------------------------------------------------------------------------------------------------------
# Shell Commands with user feedback and optional debug  formatting
#----------------------------------------------------------------------------------------------------------------------
class ShellCommandExecutor:
    """
    A class to execute shell commands with rich console output and logging.
    """

    def __init__(self, debug=False, theme=None):
        """
        Initializes the ShellCommandExecutor.

        Args:
            debug (bool, optional): Enables debug output. Defaults to False.
            theme (dict, optional): A dictionary defining the theme for rich console. Defaults to None.
        """
        if theme is None:
            theme = {
                "success": "green",
                "failure": "red",
                "warning": "yellow",
                "info": "cyan",
                "command": "cyan",
                "stdout": "white",
                "stderr": "red",
            }

        custom_theme = Theme(theme)
        self.console = Console(theme=custom_theme)
        self.debug = debug
        self.theme = theme

    def _substitute_globals(self, text):
        """
        Substitutes global variable values in the given text.

        Args:
            text (str): The text to perform substitution on.

        Returns:
            str: The text with global variables substituted.
        """
        if not isinstance(text, str):
            return text

        for name, value in globals().items():
            if isinstance(value, (int, float, str, bool)):
                text = text.replace(f"${name}", str(value))
        return text

    def execute(self, description, command, input=None, output_var=None, check_returncode=True, strict=False):
        """
        Executes a shell command.

        Args:
            description (str): Description of the command.
            command (str): The shell command to execute.
            input (str, optional): Input for the command. Defaults to None.
            output_var (str, optional): Global variable to store the output. Defaults to None.
            check_returncode (bool, optional): If True, raises an exception on non-zero return code. Defaults to True.
            strict (bool, optional): when strict is True the shell command is strict with "set -euo pipefail' (bool - optional - default False)

        Returns:
            bool: True if the command was successful, False otherwise.
        """
        description = self._substitute_globals(description)
        command = self._substitute_globals(command)
        if input: input = self._substitute_globals(input)

        try:
            # Print description to console
            self.console.print(f"[{self.theme['warning']}][ ]{description}[/{self.theme['warning']}]", end='\r')

            if self.debug:
                self.console.print(Panel(f"[{self.theme['command']}]{command}[/{self.theme['command']}]", title="Command"))

            shell_command = command
            if strict:
                shell_command = 'set -euo pipefail;' + command

            process = subprocess.Popen(
                shell_command,
                shell=True,
                stdin=subprocess.PIPE if input else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                executable='/bin/bash'
            )

            stdout, stderr = process.communicate(input=input.encode() if input else None)
            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()

            returncode = process.returncode

            if self.debug:
                output_panel = Panel(
                    Text.assemble(
                        ("STDOUT:\n", "bold"),
                        (stdout_str, self.theme['stdout']),
                        ("\n\nSTDERR:\n", "bold"),
                        (stderr_str, self.theme['stderr']),
                        style=Style(color="white")
                    ),
                    title="Output"
                )
                # Only print output when present
                if stdout_str != "" or stderr_str != "":
                    self.console.print(output_panel)

            if check_returncode and returncode != 0:
                self.console.print(f"[{self.theme['failure']}]✗ {description}[/{self.theme['failure']}]")
                logging.error(f"Command failed: {command}")
                logging.error(f"Return code: {returncode}")
                logging.error(f"Stdout: {stdout_str}")
                logging.error(f"Stderr: {stderr_str}")
                exit()  # Indicate failure
            else:
                if check_returncode:
                    self.console.print(f"[{self.theme['success']}][✓] {description}[/{self.theme['success']}]")
                else:
                    self.console.print(f"[{self.theme['warning']}][✓] {description} (return code ignored)[/{self.theme['warning']}]")

            # Store output in global variable if specified
            if output_var:
                globals()[output_var] = stdout_str
                logging.debug(f"Stored output in global variable '{output_var}'")

            logging.info(f"Command executed successfully: {command}")
            return True  # Indicate success

        except Exception:
            self.console.print(f"[{self.theme['failure']}][✗] {description}[/{self.theme['failure']}]")
            logging.exception(f"Exception while executing command: {command}")
            if self.debug:
                self.console.print_exception(show_locals=True)
            return False  # Indicate failure

    def execute_all(self, commands):
        """
        Executes a list of shell commands.

        Args:
            commands (list): A list of dictionaries, where each dictionary contains the arguments for the 'execute' method.

        Returns:
            bool: True if all commands were successful, False otherwise.
        """
        all_successful = True
        for command_data in commands:
            if not self.execute(**command_data):
                all_successful = False
        return all_successful



#----------------------------------------------------------------------------------------------------------------------
# System Functions
#----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':

#-- Create objects ------------------------------------------------------------
    console = Console(theme=theme)
    console.clear()

    prompt = Prompt()

    handler = RichHandler(
        rich_tracebacks=True,       # Show rich debug info during error
        markup=True,                # Show data as Markup
        show_time=False,            # Do not show logging time
        show_level=True,            # Do show logging level (Info, debug, etc)
        show_path=False)            # Do not show file causing log - always the same
    handler.setFormatter(CustomFormatter())

    log = logging.getLogger("rich")
    log.setLevel(logging.INFO)
    log.addHandler(handler)

    user_entry = UserEntry()

    shell = ShellCommandExecutor(debug=True)

#-- System check  -------------------------------------------------------------
    console.print(Rule("System Check"), style='success')

    # Must be in place for script to work
    SYSTEM_CHECK = True
    SYSTEM_CHECK = SYSTEM_CHECK and check_sudo()
    SYSTEM_CHECK = SYSTEM_CHECK and check_uefi()
    SYSTEM_CHECK = SYSTEM_CHECK and check_secure_boot()

    if not SYSTEM_CHECK:
        exit()

    if Prompt.ask('\nSystem configuration correct. Continue installation?', choices=['y', 'n']) == 'n':
        exit()

#-- System Preparation and Checks  --------------------------------------------
    console.print(Rule("System Preparation"), style='success')

    shell.execute('Set the time server', 'timedatectl set-ntp true')
    shell.execute('Synchronise system clock', 'hwclock --systohc --utc')
    shell.execute('Update the ISO keyring', 'pacman -Sy --noconfirm --needed archlinux-keyring')
    shell.execute('Install basic tools', 'pacman -Sy --noconfirm --needed git reflector dialog terminus-font wget mg')

#-- User Entry ----------------------------------------------------------------

    console.print(Rule("User selections for installation"), style='success')

    user_entry.configure_font()
    if not DRIVE: DRIVE = user_entry.configure_drive()
    if not SYSTEM_WIPE_DISK: SYSTEM_WIPE_DISK = user_entry.run_yesno("Disk Configuration", "Write random data to entire drive (lengthy operation)?")
    if not USER_NAME: USER_NAME = user_entry.configure_username()
    if not USER_PASSWORD: USER_PASSWORD = user_entry.configure_userpassword()
    if not LUKS_PASSWORD: LUKS_PASSWORD = user_entry.configure_lukspassword()
    if not SYSTEM_HOSTNAME: SYSTEM_HOSTNAME = user_entry.configure_hostname()
    if not SYSTEM_LOCALE: SYSTEM_LOCALE = user_entry.configure_locale()
    if not SYSTEM_KEYB: SYSTEM_KEYB = user_entry.configure_keyboard()
    if not SYSTEM_TIMEZONE: SYSTEM_TIMEZONE = user_entry.configure_timezone()
    if not SYSTEM_COUNTRY: SYSTEM_COUNTRY = user_entry.configure_country()
    if not SYSTEM_GPU_INT: SYSTEM_GPU_INT = user_entry.run_yesno('Video configuration', 'Is the GPU integrated in the CPU?[/]')

    # Get system details
    if not SYSTEM_CPU:  SYSTEM_CPU  = get_cpu_brand()
    if not SYSTEM_GPU:  SYSTEM_GPU  = get_graphics_card_brand()
    if not SYSTEM_VIRT: SYSTEM_VIRT = get_virtualizer().capitalize()

#-- User validation -----------------------------------------------------------

    console.print(Rule("Installation selections"), style='success')

    if SYSTEM_CPU:
        console.print(f'CPU .................: [green]{SYSTEM_CPU}[/]', style='info')
    else:
        console.print('CPU not detected', style='critical')

    if SYSTEM_GPU:
        console.print(f'GPU .................: [green]{SYSTEM_GPU}[/]', style='info')
    else:
        console.print('GPU not detected', style='critical')

    if SYSTEM_GPU_INT:
        console.print(f'Internal GPU ........: [green]{SYSTEM_GPU_INT}[/]', style='info')
    else:
        console.print('GPU internal not selected', style='critical')

    if SYSTEM_VIRT:
        console.print(f'Virtualiser .........: [green]{SYSTEM_VIRT}[/]', style='info')

    if DRIVE:
        console.print(f'Selected drive ......: [green]{DRIVE}[/]', style='info')
    else:
        console.print('No drive selected.', style='critical')

    if USER_NAME:
        console.print(f'Selected username ...: [green]{USER_NAME}[/]', style='info')
    else:
        console.print('No username selected.', style='critical')

    if SYSTEM_HOSTNAME:
        console.print(f'Selected hostname ...: [green]{SYSTEM_HOSTNAME}[/]', style='info')
    else:
        console.print('No hostname selected.', style='critical')

    if SYSTEM_LOCALE:
        console.print(f'Selected locale .....: [green]{SYSTEM_LOCALE}[/]', style='info')
    else:
        console.print('No locale selected.', style='critical')

    if SYSTEM_KEYB:
        console.print(f'Selected keymap .....: [green]{SYSTEM_KEYB}[/]', style='info')
    else:
        console.print('No keymap selected.', style='critical')

    if SYSTEM_TIMEZONE:
        console.print(f'Selected timezone....: [green]{SYSTEM_TIMEZONE}[/]', style='info')
    else:
        console.print('No timezone selected.', style='critical')

    if SYSTEM_COUNTRY:
        console.print(f'Selected country ....: [green]{SYSTEM_COUNTRY}[/]', style='info')
    else:
        console.print('No country selected.', style='critical')

    console.print('\n')
    console.print(f'Debugging ...........: [green]{DEBUG}[/]', style='info')
    console.print(f'Step by step ........: [green]{STEP}[/]', style='info')
    console.print(f'Wipe entire disk ....: [green]{SYSTEM_WIPE_DISK}[/]', style='info')

    if Prompt.ask('\nAre these selections correct, and continue installation?', choices=['y', 'n']) == 'n':
        exit()

#-- Disk Partitioning, Formatting and Mounting  -------------------------------
    console.print(Rule("System Installation"), style='success')

    # Write random data to the whole disk
    if SYSTEM_WIPE_DISK: shell.execute('Disk - Write random data to disk', 'dd bs=1M if=/dev/urandom of=$DRIVE', check_returncode=False)
    shell.execute('Disk - Remove file magic bytes','wipefs --all $DRIVE')

    # Create partition table and name partitions
    shell.execute('Partitioning - Create partition table', 'sgdisk --clear $DRIVE --new 1::-551MiB --new 2::0 --typecode 2:ef00 $DRIVE')
    shell.execute('Partitioning - Name the partitions', 'sgdisk $DRIVE --change-name=1:$PART_1_NAME --change-name=2:$PART_2_NAME')

    # Format partitions
    # -- partition 2 - Root  ---------------------------------------------------
    shell.execute('Partition 2 - Formatting $PART_2_NAME','mkfs.vfat -n $PART_2_NAME -F 32 $DRIVE2')

##- partition 1 ---------------------------------------------------------------
    # Unmount devices from potential previous attempts that failed
    shell.execute('Swapfiles deactivated','swapoff -a', check_returncode=False)
    shell.execute('Partitions unmounted', 'umount --recursive /mnt', check_returncode=False)
    shell.execute('Encrypted drives closed', 'cryptsetup luksClose $PART_1_UUID', check_returncode=False)
    shell.execute('Get local mirrors', 'reflector --country $SYSTEM_COUNTRY --latest 10 --sort rate --save /etc/pacman.d/mirrorlist')

    shell.execute('Partition 1 - Format to Luks $PART_1_NAME','cryptsetup luksFormat -q --type luks1 --label $PART_1_UUID $DRIVE1',input="$LUKS_PASSWORD")
    shell.execute('Partition 1 - Open $PART_1_NAME', 'cryptsetup luksOpen $DRIVE1 $PART_1_UUID' ,input="$LUKS_PASSWORD")

    shell.execute('Partition 1 - Set file system $PART_1_NAME to BTRFS', 'mkfs.btrfs --label $PART_1_UUID /dev/mapper/$PART_1_UUID')
    shell.execute('Partition 1 - Mount $PART_1_NAME', 'mount /dev/mapper/$PART_1_UUID /mnt')
    shell.execute('Partition 1 - Create subvolume @',                   'btrfs subvolume create /mnt/@')
    shell.execute('Partition 1 - Create subvolume @home',               'btrfs subvolume create /mnt/@home')
    shell.execute('Partition 1 - Create subvolume @swap',               'btrfs subvolume create /mnt/@swap')
    shell.execute('Partition 1 - Create subvolume @snapshots',          'btrfs subvolume create /mnt/@snapshots')
    shell.execute('Partition 1 - Create subvolume @home-snapshots',     'btrfs subvolume create /mnt/@home-snapshots')
    shell.execute('Partition 1 - Create subvolume @cache-pacman-pkgs',  'btrfs subvolume create /mnt/@cache-pacman-pkgs')
    shell.execute('Partition 1 - Create subvolume @var',                'btrfs subvolume create /mnt/@var')
    shell.execute('Partition 1 - Create subvolume @var-lib-libvirt',    'btrfs subvolume create /mnt/@libvirt')
    shell.execute('Partition 1 - Create subvolume @var-lib-docker',     'btrfs subvolume create /mnt/@docker')
    shell.execute('Partition 1 - Create subvolume @var-log',            'btrfs subvolume create /mnt/@var-log')
    shell.execute('Partition 1 - Create subvolume @var-tmp',            'btrfs subvolume create /mnt/@var-tmp')
    shell.execute('Partition 1 - Umount $PART_1_NAME', 'umount /mnt')

    # Copy-on-Write is not good for big files that are written multiple times.
    # This includes: logs, containers, virtual machines, databases, etc.
    # They usually lie in /var, therefore CoW will be disabled for everything in /var
    # Note that currently btrfs does not support the nodatacow mount option.
    shell.execute('Partition 1 - Mount @',                  'mount         -o subvol=@,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt')
    shell.execute('Partition 1 - Mount @home',              'mount --mkdir -o subvol=@home,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/home')
    shell.execute('Partition 1 - Mount @swap',              'mount --mkdir -o subvol=@swap,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/.swap')
    shell.execute('Partition 1 - Mount @snaphots',          'mount --mkdir -o subvol=@snapshots,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/.snapshots')
    shell.execute('Partition 1 - Mount @home-snapshots',    'mount --mkdir -o subvol=@home-snapshots,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/home/.snaphots')
    shell.execute('Partition 1 - Mount @var',               'mount --mkdir -o subvol=@var,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/var')

    shell.execute('Partition 1 - Disable CoW on /var/',  'chattr +C /mnt/var')
    shell.execute('Partition 1 - Mount @var-log',           'mount --mkdir -o subvol=@var-log,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/var/log')
    shell.execute('Partition 1 - Mount @var-tmp',           'mount --mkdir -o subvol=@var-tmp,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/var/tmp')
    shell.execute('Partition 1 - Mount @var-lib-libvirt',   'mount --mkdir -o subvol=@libvirt,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/var/lib/libvirt')
    shell.execute('Partition 1 - Mount @var-lib-docker',    'mount --mkdir -o subvol=@docker,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/var/lib/docker')
    shell.execute('Partition 1 - Mount @cache-pacman-pkgs', 'mount --mkdir -o subvol=@cache-pacman-pkgs,$BTRFS_MOUNT_OPT /dev/mapper/$PART_1_UUID /mnt/cache/pacman/pkgs')

##- partition 2 ---------------------------------------------------------------

    shell.execute('Partition 2 - Mount "/mnt/efi"',         'mount --mkdir -o umask=0077 $DRIVE2 /mnt/efi')

##- swap file -----------------------------------------------------------------

    shell.execute('Swapfile creation','btrfs filesystem mkswapfile /mnt/.swap/swapfile')
    # Faults occasionally, and documentation indicates not necessary
    # shell.execute('Swapfile make','mkswap /mnt/.swap/swapfile')
    shell.execute('Swapfile on','swapon /mnt/.swap/swapfile')

#-- Install Linux Packages  ---------------------------------------------------

    # Driver packages all opensource / check on virtualbox
    packages = get_packages_from_file('packages/pacman')
    if SYSTEM_CPU  == 'Intel'  : packages.append('intel-ucode')
    if SYSTEM_CPU  == 'AMD'    : packages.append('amd-ucode')
    if SYSTEM_VIRT == 'Oracle' : packages.append('virtualbox-guest-utils')
    if SYSTEM_VIRT == 'VMWare' : packages.append('open-vm-tools')

    # Only install open-source GPU drivers if not in virtualiser
    if SYSTEM_VIRT == 'metal':
        if SYSTEM_GPU == 'Intel'   : packages.append('vulkan-intel', 'intel-media-driver')
        if SYSTEM_GPU == 'AMD'     : packages.append('vulkan-radeon')
        if SYSTEM_GPU == 'NVIDIA'  : packages.append('vulkan-nouveau')

    SYSTEM_PKGS = ' '.join(packages)
    shell.execute('Installing Linux packages .... (patience)', 'pacstrap -K /mnt $SYSTEM_PKGS')

#-- Copy config files  --------------------------------------------------------

    copy_file_structure('rootfs', '/mnt')

#-- Patch config files  -------------------------------------------------------

    shell.execute('Copy mirror list', 'cp /etc/pacman.d/mirrorlist /mnt/etc/pacman.d/')
    shell.execute('Patch pacman configuration -colours', 'sed -i "s/#Color/Color/g" /mnt/etc/pacman.conf')
    shell.execute('Patch qemu configuration - user', 'sed -i "s/username_placeholder/$USER_NAME/g" /mnt/etc/libvirt/qemu.conf')
    shell.execute('Patch tty configuration - user', 'sed -i "s/username_placeholder/$USER_NAME/g" /mnt/etc/systemd/system/getty@tty1.service.d/autologin.conf')
    shell.execute('Patch shell - dash', 'ln -sfT dash /mnt/usr/bin/sh')

#-- Write Kernel Command Line  ------------------------------------------------

    # Note: Erwin cryptedevice :UUID or archlinux?
    SYSTEM_CMD = [
        'lsm=landlock,lockdown,yama,integrity,apparmor,bpf', # Customize Linux Security Modules to include AppArmor
        'lockdown=integrity',                                # Put kernel in integrity lockdown mode
        f'cryptdevice={DRIVE}1:{PART_1_UUID}',               # The LUKS device to decrypt
        f'root=/dev/mapper/{PART_1_UUID}',                   # The decrypted device to mount as the root
        'rootflags=subvol=@',                                # Mount the @ btrfs subvolume inside the decrypted device as the root
        'mem_sleep_default=deep',                            # Allow suspend state (puts device into sleep but keeps powering the RAM for fast sleep mode recovery)
        'audit=1',                                           # Ensure that all processes that run before the audit daemon starts are marked as auditable by the kernel
        'audit_backlog_limit=32768',                         # Increase default log size
        'quiet splash rd.udev.log_level=3'                   # Completely quiet the boot process to display some eye candy using plymouth instead :)
    ]

    with open('/mnt/etc/kernel/cmdline', 'a') as f: f.write(' '.join(SYSTEM_CMD) + '\n')

#-- Set Locale etc  -----------------------------------------------------------

    shell.execute('Set the system font to "$SYSTEM_FONT"', 'echo "FONT=$SYSTEM_FONT" >/mnt/etc/vconsole.conf')
    shell.execute('Set the system keyboard to "$SYSTEM_KEYB"', 'echo "KEYMAP=$SYSTEM_KEYB" >>/mnt/etc/vconsole.conf')
    shell.execute('Set the hostname to $SYSTEM_HOSTNAME', 'echo "$SYSTEM_HOSTNAME" >/mnt/etc/hostname')
    shell.execute('Set the language to $SYSTEM_LOCALE', 'echo "$SYSTEM_LOCALE" >>/mnt/etc/locale.gen')
    shell.execute('Set the timezone to $SYSTEM_TIMEZONE', 'ln -sf /usr/share/zoneinfo/$SYSTEM_TIMEZONE /mnt/etc/localtime')
    shell.execute('Generate locale', 'arch-chroot /mnt locale-gen')

#-- Generate fstab  -----------------------------------------------------------

    shell.execute('Generate fstab', 'genfstab -U /mnt >>/mnt/etc/fstab')

#-- Configure Plymouth  -------------------------------------------------------

    shell.execute('Suppress login screens', 'touch /mnt/etc/hushlogins')
    shell.execute('Clean login experience on TTY and SSH', "sed -i 's/^HUSHLOGIN_FILE.*/#&/g' /mnt/etc/login.defs")

#-- User and Group accounts  --------------------------------------------------

    # Create user (USER_NAME), set shell to Bourne Shell (dash), create home folder
    shell.execute('Add user account for $USER_NAME', 'arch-chroot /mnt useradd -m -s /bin/sh $USER_NAME')
    # Force creation of system groups (for services)
    shell.execute('Create group wheel', 'arch-chroot /mnt groupadd -rf wheel')
    shell.execute('Create group audit', 'arch-chroot /mnt groupadd -rf audit')
    shell.execute('Create group libvirt', 'arch-chroot /mnt groupadd -rf libvirt')
    shell.execute('Create group firejail', 'arch-chroot /mnt groupadd -rf firejail')
    shell.execute('Create group allow-internet', 'arch-chroot /mnt groupadd -rf allow-internet')
    # Add user (USER_NAME) to system groups
    shell.execute('Add $USER_NAME to wheel', 'arch-chroot /mnt gpasswd -a $USER_NAME wheel')
    shell.execute('Add $USER_NAME to audit', 'arch-chroot /mnt gpasswd -a $USER_NAME audit')
    shell.execute('Add $USER_NAME to libvirt', 'arch-chroot /mnt gpasswd -a $USER_NAME libvirt')
    shell.execute('Add $USER_NAME to firejail', 'arch-chroot /mnt gpasswd -a $USER_NAME firejail')
    # Set user (USER_NAME) password
    shell.execute('Set password for $USER_NAME', 'arch-chroot /mnt chpasswd', input='$USER_NAME:$USER_PASSWORD\n')

#-- Install AUR helper --------------------------------------------------------

    shell.execute('Set NOPASSWD sudo to users', 'echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" >>/mnt/etc/sudoers')
    shell.execute('Disable pacman wrapper', 'mv /mnt/usr/local/bin/pacman /mnt/usr/local/bin/pacman.disable')

    # command = textwrap.dedent(f"""\
    # arch-chroot -u $USER_NAME /mnt /bin/sh -c 'mkdir /tmp/yay.$$ &&
    # cd /tmp/yay.$$ &&
    # curl https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=yay-bin -o PKGBUILD &&
    # -c makepkg -si --noconfirm'
    # """).strip()

    command =  f"""arch-chroot -u {USER_NAME} /mnt /bin/sh -c 'mkdir /tmp/yay.$$ && cd /tmp/yay.$$ && curl "https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=yay-bin" -o PKGBUILD && makepkg -si --noconfirm'"""

    shell.execute('Install AUR helper', command)

#-- Install Aur Packages  -----------------------------------------------------

    # Driver packages all opensource / check on virtualbox
    packages = get_packages_from_file('packages/aur')

    if SYSTEM_VIRT == 'metal':
        if SYSTEM_GPU == 'NVIDIA'  : packages.append('nouveau-fw')

    SYSTEM_PKGS = ' '.join(packages)
    shell.execute('Installing Aur packages ....(patience)', 'HOME="/home/$USER_NAME" arch-chroot -u "$USER_NAME" /mnt /usr/bin/yay --noconfirm -Sy $SYSTEM_PKGS')

    shell.execute('Remove pacman wrapper', 'mv /mnt/usr/local/bin/pacman.disable /mnt/usr/local/bin/pacman')
    shell.execute('Remove NOPASSWD sudo from users', "sed -i '$ d' /mnt/etc/sudoers")

#-- Install Login -------------------------------------------------------------

    shell.execute('Installing Login screen', 'arch-chroot /mnt plymouth-set-default-theme splash')

#-- Installing RAM Disk Image -------------------------------------------------

    if SYSTEM_GPU ==  'AMD':
        SYSTEM_MODULES = 'amdgpu'
    elif SYSTEM_GPU == 'NVIDEA':
        SYSTEM_MODULES = 'nouvea'
    elif SYSTEM_CPU == 'Intel' and SYSTEM_GPU == 'Intel':
        SYSTEM_MODULES = 'i915'
    else:
        SYSTEM_MODULES = ''

    SYSTEM_CMD = [
        f'MODULES=({SYSTEM_MODULES})',
        'BINARIES=(setfont)',
        'FILES=()',
        'HOOKS=(base consolefont keymap udev autodetect modconf block plymouth encrypt filesystems keyboard)'
    ]

    # Overwrite the config file with the SYSTEM_CMD data
    with open('/mnt/etc/mkinitcpio.conf', 'w') as f: f.write('\n'.join(SYSTEM_CMD) + '\n')
    shell.execute('Creating the initial RAM disk image', 'arch-chroot /mnt mkinitcpio -p linux-hardened')


# -- Generate UEFI keys, sign kernels, enroll keys ----------------------------

    shell.execute('Configure Linux Hardened', "echo 'KERNEL=linux-hardened' >/mnt/etc/arch-secure-boot/config")
    shell.execute('Install Linux Hardened', 'arch-chroot /mnt arch-secure-boot initial-setup')

# -- Hardening ----------------------------------------------------------------

    shell.execute('Hardening /boot partition', 'arch-chroot /mnt chmod 700 /boot')
    shell.execute('Disabling root user', 'arch-chroot /mnt passwd -dl root')

# -- Configuring Firejail -----------------------------------------------------

    shell.execute('Configure firejail', 'arch-chroot /mnt /usr/bin/firecfg')
    shell.execute('Enable firejail for $USER_NAME', 'echo "$USER_NAME" >/mnt/etc/firejail/firejail.users')

# -- Configuring DNS ----------------------------------------------------------

    shell.execute('Remove default resolv.conf', 'rm -f /mnt/etc/resolv.conf')
    shell.execute('Install resolv.conf', 'arch-chroot /mnt ln -s /usr/lib/systemd/resolv.conf /etc/resolv.conf')

# -- Configuring Systemd services ---------------------------------------------

    shell.execute('Configure systemd service - systemd-networkd', 'arch-chroot /mnt systemctl enable systemd-networkd')
    shell.execute('Configure systemd service - systemd-resolved', 'arch-chroot /mnt systemctl enable systemd-resolved')
    shell.execute('Configure systemd service - systemd-timesyncd', 'arch-chroot /mnt systemctl enable systemd-timesyncd')
    shell.execute('Configure systemd service - getty@tty1', 'arch-chroot /mnt systemctl enable getty@tty1')
    shell.execute('Configure systemd service - dbus-broker', 'arch-chroot /mnt systemctl enable dbus-broker')
    shell.execute('Configure systemd service - iwd', 'arch-chroot /mnt systemctl enable iwd')
    shell.execute('Configure systemd service - auditd', 'arch-chroot /mnt systemctl enable auditd')
    shell.execute('Configure systemd service - nftables', 'arch-chroot /mnt systemctl enable nftables')
    shell.execute('Configure systemd service - docker', 'arch-chroot /mnt systemctl enable docker')
    shell.execute('Configure systemd service - libvirtd', 'arch-chroot /mnt systemctl enable libvirtd')
    shell.execute('Configure systemd service - check-secure-boot', 'arch-chroot /mnt systemctl enable check-secure-boot')
    shell.execute('Configure systemd service - apparmor', 'arch-chroot /mnt systemctl enable apparmor')
    shell.execute('Configure systemd service - auditd-notify', 'arch-chroot /mnt systemctl enable auditd-notify')
    shell.execute('Configure systemd service - local-forwarding-proxy', 'arch-chroot /mnt systemctl enable local-forwarding-proxy')

# -- Configuring Systemd timers -----------------------------------------------

    shell.execute('Configure systemd timer - snapper-timeline.timer', 'arch-chroot /mnt systemctl enable snapper-timeline.timer')
    shell.execute('Configure systemd timer - snapper-cleanup.timer', 'arch-chroot /mnt systemctl enable snapper-cleanup.timer')
    shell.execute('Configure systemd timer - auditor.timer', 'arch-chroot /mnt systemctl enable auditor.timer')
    shell.execute('Configure systemd timer - btrfs-scrub@-.timer', 'arch-chroot /mnt systemctl enable btrfs-scrub@-.timer')
    shell.execute('Configure systemd timer - btrfs-balance.timer', 'arch-chroot /mnt systemctl enable btrfs-balance.timer')
    shell.execute('Configure systemd timer - pacman-sync.timer', 'arch-chroot /mnt systemctl enable pacman-sync.timer')
    shell.execute('Configure systemd timer - pacman-notify.timer', 'arch-chroot /mnt systemctl enable pacman-notify.timer')
    shell.execute('Configure systemd timer - should-reboot-check.timer', 'arch-chroot /mnt systemctl enable should-reboot-check.timer')

# -- Configuring Systemd user services ----------------------------------------

    shell.execute('Configure systemd user service - dbus-broker', 'arch-chroot /mnt systemctl --global enable dbus-broker')
    shell.execute('Configure systemd user service - journalctl-notify', 'arch-chroot /mnt systemctl --global enable journalctl-notify')
    shell.execute('Configure systemd user service - pipewire', 'arch-chroot /mnt systemctl --global enable pipewire')
    shell.execute('Configure systemd user service - wireplumber', 'arch-chroot /mnt systemctl --global enable wireplumber')
    shell.execute('Configure systemd user service - gammastep', 'arch-chroot /mnt systemctl --global enable gammastep')

# -- Installing dotfiles  -----------------------------------------------------


    command = f"""HOME='/home/{USER_NAME}' arch-chroot -u $USER_NAME /mnt /bin/bash -c 'cd && git clone https://github.com/echjansen/.dotfiles && .dotfiles/install.sh'"""

    shell.execute('Install dotfiles ....(patience)', command)

# -- Done ---------------------------------------------------------------------

    if prompt.ask("[green]Installation complete successfully. Reboot?[/]", choices=['y', 'n']) == 'y':
        shell.execute('Swapfile off','swapoff -a')
        shell.execute('Partitions - Umount', 'umount --recursive /mnt')
        shell.execute('Partition 1 - Close Luks', 'cryptsetup luksClose $PART_1_UUID')
        shell.execute('Rebooting', 'reboot now')
