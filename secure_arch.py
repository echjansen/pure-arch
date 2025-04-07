#----------------------------------------------------------------------------------------------------------------------
# Goals:
# - Use python script to install Arch Linux
#----------------------------------------------------------------------------------------------------------------------
# Todos:
# - [X] Selecting 'USER_COUNTRY'
# - [ ] Is it better to use UUID instead of disk name? LuksOpen / LuksClose / fstab
# - [ ]
# - [ ]
#----------------------------------------------------------------------------------------------------------------------

import os
import shutil
import logging
import subprocess
from typing import List
from rich.console import Console
from rich.theme import Theme
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.logging import RichHandler
from rich.progress import Progress
from typing import Union, Tuple

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
        'ERROR':     'bold reverse red',
        'DEBUG':     'blue',
        'CRITICAL':  'red',
        }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, 'white')
        record.msg = f'[{log_color}]{record.msg}[/{log_color}]'
        return super().format(record)

console = Console(theme=theme)
prompt = Prompt()
handler = RichHandler(rich_tracebacks=True, markup=True)
handler.setFormatter(CustomFormatter())
log = logging.getLogger("rich")
log.addHandler(handler)
log.setLevel(logging.DEBUG)

# Debugging variables
DEBUG = True                   # If True, report on command during execution
STEP = False                   # If true, step one command at the time

# Global Constants
PART_1_NAME = "Primary"
PART_2_NAME = "ESP"
BTRFS_MOUNT_OPT = "defaults,noatime,nodiratime,compress=zstd,space_cache=v2"

LINUX_ENV = "LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 KEYMAP=us DEBIAN_FRONTEND=noninteractive TERM=xterm-color"
LINUX_PKGS = "linux-image-amd64 firmware-linux firmware-iwlwifi zstd grub-efi cryptsetup cryptsetup-initramfs btrfs-progs fdisk gdisk sudo network-manager xserver-xorg xinit lightdm xfce4 dbus-x11 thunar xfce4-terminal firefox-esr keepassxc network-manager-gnome mg"

# Global Variables
DRIVE = None                    # The device that will be made into a backup device
DRIVE_PASSWORD = None           # Encryption password for partitions
PART_1_UUID = None              # UUID of partition 1
PART_2_UUID = None              # UUID of partition 2
USER_NAME = None                # User name for backup devices (no root)
USER_PASSWORD = None            # User password for backup device
LUKS_PASSWORD = None            # Luks password for drive(s)
SYSTEM_LOCALE = None            # System locale ('en_US')
SYSTEM_CHARMAP = None           # System keyboard layout ('UTF-8')
SYSTEM_COUNTRY = None           # System country ('Australia')
SYSTEM_COUNTRY_CODE = None      # System country code ('au')
SYSTEM_TIMEZONE = None          # System timezone, used for repository downloads
SYSTEM_CPU = None               # System CPU brand (Intel, AMD, etc)
SYSTEM_GPU = None               # System GPU brand (Intel, AMD, NVIDIA, etc)
SYSTEM_VIRT = None              # System virtualizer (if any) (oracle, vmware, docker, etc)
SYSTEM_PKGS = None              # System packages to install
SYSTEM_CMD = None               # System commands lines

# Deleteme
DRIVE = '/dev/sdb'              # The device that will be made into a backup device
DRIVE_PASSWORD = '123'          # Encryption password for partitions
USER_NAME = 'echjansen'         # User name for backup devices (no root)
USER_PASSWORD = '123'           # User password for backup device
LUKS_PASSWORD = '123'           # Luks password for drive(s)
SYSTEM_LOCALE = 'en_US'         # System locale ('en_US')
SYSTEM_CHARMAP = 'UTF-8'        # System keyboard layout ('UTF-8')
SYSTEM_COUNTRY = 'Australia'    # System country ('Australia')
SYSTEM_COUNTRY_CODE = 'au'      # System country code ('au')
SYSTEM_TIMEZONE  = 'Australia\Melbourne'   # System timezone

#----------------------------------------------------------------------------------------------------------------------
# Supporting functions
#----------------------------------------------------------------------------------------------------------------------
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

    try:
        # Check if the source directory exists
        if not os.path.isdir(source):
            source = find_subdirectory(source)
            if not source:
                console.print(f"Error: Source directory '{source}' not found.", style='error')
                return

        # Create the destination directory if it doesn't exist
        os.makedirs(destination, exist_ok=True)  # exist_ok=True prevents an error if the directory already exists

        total_files = sum(len(files) for _, _, files in os.walk(source))

        with Progress() as progress:
            task = progress.add_task("[green]Copying files...", total=total_files)

            for root, _, files in os.walk(source):
                # Create the corresponding directory structure in the destination
                dest_dir = os.path.join(destination, os.path.relpath(root, source))
                os.makedirs(dest_dir, exist_ok=True)

                for file in files:
                    source_file = os.path.join(root, file)
                    dest_file = os.path.join(dest_dir, file)
                    try:
                        shutil.copy2(source_file, dest_file)  # copy2 preserves metadata
                        progress.update(task, advance=1)
                    except Exception as e:
                        console.print(f"Warning: Could not copy '{source_file}' to '{dest_file}': {e}", style='error')

    except Exception as e:
        console.print(f"An unexpected error occurred: {e}", style='critical')

def write_config_to_file(config_lines: List[str], target_file: str) -> None:
    """
    Writes a list of configuration lines to a target file, appending each line with a newline.
    Creates the file if it does not exist.

    Args:
        config_lines: A list of strings, where each string represents a configuration line.
        target_file: The path to the file to write the configuration lines to.
    """
    try:
        with open(target_file, 'a') as f:  # Open in append mode ('a') - creates the file if it does not exist
            for line in config_lines:
                f.write(line + '\n')  # Append each line with a newline

    except Exception as e:
        console.print(f"Error writing to '{target_file}': {e}", style='critical')

def select_from_directory_with_search(directory: str, item_type: str, remove_extension: bool = False) -> str:
    """
    Lists and allows the user to select an item from a directory, with a search function.

    Args:
        directory: The directory to list items from.
        item_type: The type of item (e.g., "locale", "charmap") for display purposes.

        remove_extension: Whether to remove the extension from the displayed item names.

    Returns:
        str: The selected item name.
             Returns an empty string if no item is selected or an error occurs.
    """

    try:
        if not os.path.isdir(directory):
            console.print(f"[bold red]Error: {directory} not found.[/]")
            return ""

        all_items = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        all_items.sort()

        if not all_items:
            console.print(f"No {item_type}s found in {directory}.", style='error')
            return ""

        def filter_items(items: List[str], search_term: str) -> List[str]:
            search_term = search_term.lower()
            return [item for item in items if search_term in item.lower()]

        while True:
            search_term = prompt.ask(f"[yellow]Enter search term for {item_type} (or press Enter to list all)[/]")

            filtered_items = filter_items(all_items, search_term) if search_term else all_items

            if not filtered_items:
                console.print("[bold red]No matching items found. Please try again.[/]")
                continue

            table = Table(title=f"Available {item_type.capitalize()}s")
            table.add_column("Index", justify="right", style="success", no_wrap=True)
            table.add_column(item_type.capitalize(), style="success")

            display_items = [os.path.splitext(item)[0] for item in filtered_items] if remove_extension else filtered_items

            for i, item in enumerate(display_items):
                table.add_row(str(i + 1), item)

            console.print(table)

            selection = prompt.ask(f"[yellow]Enter the index of the {item_type} to select (or press Enter to search again):[/]", default="", show_default=False)

            if not selection:
                continue  # Go back to search

            try:
                index = int(selection) - 1
                if 0 <= index < len(filtered_items):
                    return display_items[index]
                else:
                    console.print("[bold red]Invalid selection. Please enter a valid index.[/]")
            except ValueError:
                console.print("[bold red]Invalid input. Please enter a number or press Enter to search again.[/]")

    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/]")
        return ""

def select_from_list_with_search(items: List[str], item_type: str) -> str:
    """
    Lists and allows the user to select an item from a list, with a search function.

    Args:
        items: The list of items to select from.
        item_type: The type of item (e.g., "country", "place") for display purposes.

    Returns:
        The selected item, or an empty string if no item is selected.
    """

    def filter_items(items: List[str], search_term: str) -> List[str]:
        search_term = search_term.lower()
        return [item for item in items if search_term in item.lower()]

    while True:
        search_term = Prompt.ask(f"[yellow]Enter search term for {item_type} (or press Enter to list all):[/]")

        filtered_items = filter_items(items, search_term) if search_term else items

        if not filtered_items:
            console.print("[bold red]No matching items found. Please try again.[/]")
            continue

        table = Table(title=f"Available {item_type.capitalize()}s")
        table.add_column("Index", justify="right", style="success", no_wrap=True)
        table.add_column(item_type.capitalize(), style="success")

        for i, item in enumerate(filtered_items):
            table.add_row(str(i + 1), item)

        console.print(table)

        selection = Prompt.ask(f"[yellow]Enter the index of the {item_type} to select (or press Enter to search again):[/]", default="", show_default=False)

        if not selection:
            continue  # Go back to search

        try:
            index = int(selection) - 1
            if 0 <= index < len(filtered_items):
                return filtered_items[index]
            else:
                console.print("[bold red]Invalid selection. Please enter a valid index.[/]")
        except ValueError:
            console.print("[bold red]Invalid input. Please enter a number or press Enter to search again.[/]")

def load_timezone_data(zoneinfo_dir: str = "/usr/share/zoneinfo") -> List[Tuple[str, str]]:
    """
    Loads timezone data from the /usr/share/zoneinfo directory.

    Args:
        zoneinfo_dir: The directory containing the timezone data.

    Returns:
        A list of tuples, where each tuple contains (Country, Place).
        Returns an empty list if an error occurs.
    """
    timezones: List[Tuple[str, str]] = []

    try:
        for country in os.listdir(zoneinfo_dir):
            country_path = os.path.join(zoneinfo_dir, country)
            if os.path.isdir(country_path) and country not in ["posix", "right"]:  # Exclude posix and right directories
                for place in os.listdir(country_path):
                    place_path = os.path.join(country_path, place)
                    if os.path.isfile(place_path):
                        timezones.append((country, place))
        return timezones
    except FileNotFoundError:
        print(f"Error: Timezone directory '{zoneinfo_dir}' not found.")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def check_sudo():
    """
    Check that the software is running with sudo privileges.
    If not, exit.
    """

    if os.getegid() != 0:
        console.print("Run this application with sudo privilege.", style="error")
        exit()

def select_drive() -> str:
    """
    Prompts the user to select a drive from the available block devices.

    Uses lsblk and udevadm to gather device information and Rich library for interactive
    console display and input.  Only returns the device path, the model is only shown
    on the selection table.

    Returns:
        str: The full device name (e.g., "/dev/sda").
             Returns "" if no valid device is selected or if an error occurs.
    """

    try:
        # Execute lsblk to get block device information
        result = subprocess.run(
            ['lsblk', '-d', '-n', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT'],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()
        devices: List[Tuple[str, str, str]] = []  # List of (name, size, mountpoint) tuples
        for line in output.splitlines():
            parts = line.split()
            name = parts[0]
            size = parts[1]
            type = parts[2]
            mountpoint = " ".join(parts[3:]) if len(parts) > 3 else ""  # Handles missing mountpoints
            if type == 'disk':  # Only consider disks
                devices.append((name, size, mountpoint))

        if not devices:
            console.print('No available disks found.', style='error')
            return ""

        device_models = {}  # Store device models, by name
        for name, _, _ in devices:
            try:
                # Use udevadm to get the device model
                udevadm_result = subprocess.run(
                    ['udevadm', 'info', '--query=property', f'--name=/dev/{name}'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                udevadm_output = udevadm_result.stdout.strip()
                model = None
                for line in udevadm_output.splitlines():
                    if line.startswith('ID_MODEL='):
                        model = line[len('ID_MODEL='):].strip()
                        break
                device_models[name] = model if model else "Unknown Model"

            except subprocess.CalledProcessError:
                device_models[name] = "Unknown Model"
            except Exception as e:
                device_models[name] = "Unknown Model"


        # Display the available drives in a table
        table = Table(title="Available Disks")
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        table.add_column("Device Name", style="success")
        table.add_column("Size", style="success")
        table.add_column("Mountpoint", style="success")
        table.add_column("Model", style="success")

        for i, (name, size, mountpoint) in enumerate(devices):
            table.add_row(
                str(i + 1),
                f"/dev/{name}",
                size,
                mountpoint if mountpoint != '' else '[italic]None[/]',
                device_models[name]  # Add the device model
            )

        console.print(table)

        # Prompt the user to select a drive
        while True:
            try:
                selection = Prompt.ask(
                    "[yellow]Enter the index of the drive to select[/]",
                    default="1",
                    show_default=True
                )
                index = int(selection) - 1

                if 0 <= index < len(devices):
                    selected_device = devices[index][0]
                    return f"/dev/{selected_device}"  # Only return device path now.
                else:
                    console.print('Invalid selection. Please enter a valid index.', style='error')
            except ValueError:
                console.print('Invalid input. Please enter a number.', style='error')

    except subprocess.CalledProcessError as e:
        console.print(f'Error executing lsblk: {e}', style='critical')
        return ""
    except Exception as e:
        console.print(f'An unexpected error occurred: {e}', style='critical')
        return ""

def select_password(user_prompt: str, min_length: int = 8) -> str:
    '''
    Prompts the user to enter a password twice for confirmation, hiding the input
    on the console. It retries until the two entries match and meet the minimum length requirement.

    Args:
        user_prompt (str): The prompt for the user to indicate what password is asked.
        min_length (int):  The minimum length required for the password. Defaults to 8.

    Returns:
        str: The confirmed password.
    '''

    while True:
        password = prompt.ask(f'[yellow]Enter the password for {user_prompt} (minimum {min_length} characters)[/]', password=True)
        if len(password) < min_length:
            console.print(f'Password must be at least {min_length} characters long. Please try again.', style='error')
            continue

        password_confirmation = prompt.ask(f'[yellow]Confirm the password for {user_prompt}[/]', password=True)

        if password == password_confirmation:
            return password
        else:
            console.print('Passwords do not match. Please try again.', style='error')

def select_username() -> str:
    '''
    Prompts the user to enter a username. The username cannot be empty.
    it continues prompting until a non-empty username is provided.

    Returns:
        str: The entered username.
    '''
    while True:
        username = prompt.ask('[yellow]Enter username[/]')

        if username.strip():
            return username.strip()
        else:
            console.print('[bold red]Username cannot be empty. Try again.[/]')

def select_country() -> Tuple[str, str]:
    """
    Uses the 'reflector --list-countries' command to display a list of countries
    and allows the user to select one.

    Returns:
        Tuple[str, str]: A tuple containing the selected country name and code.
                         Returns ("", "") if no country is selected or an error occurs.
    """

    try:
        # Execute reflector --list-countries
        result = subprocess.run(
            ['reflector', '--list-countries'],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()
        lines = output.splitlines()

        # Skip the header lines (based on the example output)
        lines = lines[2:]  # Skip first 2 lines

        countries: List[Tuple[str, str, str]] = []  # List of (Country, Code, Count) tuples
        for line in lines:
            parts = line.split(maxsplit=2)  # Split into 3 parts max
            if len(parts) == 3:
                country, code, count = parts
                countries.append((country.strip(), code.strip(), count.strip()))

        if not countries:
            console.print("No countries found by reflector.", style='error')
            return "", ""

        # Display the countries in a table
        table = Table(title="Available Countries")
        table.add_column("Index", justify="right", style="success", no_wrap=True)
        table.add_column("Country", style="success")
        table.add_column("Code", style="success")
        table.add_column("Count", style="success")

        for i, (country, code, count) in enumerate(countries):
            table.add_row(str(i + 1), country, code, count)

        console.print(table)

        # Prompt the user to select a country
        while True:
            try:
                selection = Prompt.ask(
                    "[yellow]Enter the index of the country to select:[/]",
                    default="1",
                    show_default=True
                )
                index = int(selection) - 1

                if 0 <= index < len(countries):
                    selected_country, selected_code, _ = countries[index]  # Get country and code
                    return selected_country, selected_code.lower()
                else:
                    console.print("Invalid selection. Please enter a valid index.", style='error')
            except ValueError:
                console.print("Invalid input. Please enter a number.", style='error')

    except subprocess.CalledProcessError as e:
        console.print(f"Error executing reflector: {e}", style='error')
        return "", ""
    except FileNotFoundError:
        console.print("Error: reflector command not found. Please ensure reflector is installed.", style='critical')
        return "", ""
    except Exception as e:
        console.print(f"An unexpected error occurred: {e}", style='critical')
        return "", ""

def select_locale() -> str:
    """
    Lists and allows the user to select a locale from /usr/share/i18n/locales, with a search function.

    Returns:
        str: The selected locale name (e.g., "en_US").
             Returns an empty string if no locale is selected or an error occurs.
    """
    return select_from_directory_with_search("/usr/share/i18n/locales", "Language (example: en_US)")


def select_charmap() -> str:
    """
    Lists and allows the user to select a charmap from /usr/share/i18n/charmaps, with a search function.

    Returns:
        str: The selected charmap name (e.g., "UTF-8").
             Returns an empty string if no charmap is selected or an error occurs.
    """
    return select_from_directory_with_search("/usr/share/i18n/charmaps", "Character Map (example: UTF-8)", remove_extension=True)


def select_timezone() -> str:
    """
    Prompts the user to select a timezone in the format "Country/Place".

    Returns:
        The selected timezone string, or an empty string if no timezone is selected.
    """

    timezones = load_timezone_data()

    if not timezones:
        return ""

    while True:
        country = select_from_list_with_search(sorted(list(set([tz[0] for tz in timezones]))), "country")
        if not country:
            return ""

        # Filter places based on the selected country
        places = [tz[1] for tz in timezones if tz[0] == country]
        place = select_from_list_with_search(sorted(places), "place")
        if not place:
            continue  # Go back to country selection if no place is selected

        console.print(f"Selected timezone: {country}/{place}", style='success')
        return f"{country}/{place}"


def run_bash(description :str, command :str, input=None, output_var=None,  **kwargs):
    '''
    Execute a bash command with optional input from stdin and return the return code, output and error
    '''

    # Step when debugging
    if STEP == True:
        if prompt.ask(f"{description}", choices=['y', 'n']) == 'n': exit()

    # Ensure arguments are well formatted
    if not isinstance(description, str):
        log.error("The Description must be a string")
        raise ValueError("The Description must be a string")

    if not isinstance(command, str):
        log.error("The command must be a string")
        raise ValueError("The command must be a string")

    if input is not None and not isinstance(input, str):
        log.error("The Input must be s string")
        raise ValueError("The Input must be a string")

    if output_var is not None and not isinstance(output_var, str):
        log.error("The Output name must be s string")
        raise ValueError("The Output name must be a string")

    # Format "command" with potential values of global variables
    try:
        global_vars = {key: value for key, value in globals().items() if not key.startswith('__')}
        command_formatted = command.format(**global_vars)
    except KeyError as e:
        log.error(f'Missing variable for command: {e}')
        raise ValueError(f'Missing variable for command: {e}')

    # Format "description" with potential values of global variables
    try:
        description_formatted = description.format(**global_vars)
    except KeyError as e:
        log.error(f'Missing variable for description: {e}')
        raise ValueError(f'Missing variable for description: {e}')

    # Format input with potential values of global variables
    try:
        input_formatted = None
        if input is not None:
            input_formatted = input.format(**global_vars)
    except KeyError as e:
        log.error(f'Missing variable for input: {e}')
        raise ValueError(f'Missing variable for input: {e}')

    # Report running of the command
    log.info(f'{description_formatted}')
    if DEBUG: log.debug(f'{command_formatted}')

    try:
        # Run the bash command
        result = subprocess.run(command_formatted, shell=True, check=True, stdout=subprocess.PIPE,
                                input=input_formatted, stderr=subprocess.PIPE, text=True)

        # Set return variable if specified
        if output_var in globals():
            globals()[output_var] = result.stdout.strip()
            if DEBUG: log.debug(f'Variable: {output_var} - value: {globals()[output_var]}')

        # Standard function returns
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    except subprocess.CalledProcessError as e:
        log.error(f'Command: {command_formatted}')
        log.error(f'Return code: {e.returncode}')
        log.error(f'Error output: {e.stderr.strip()}')
        if prompt.ask('Exit?', choices=['y', 'n']) == 'y':
            exit()
        return e.returncode, e.output.strip(), e.stderr.strip()

    except Exception as e:
        log.exception('An unexpected error occurred')
        return -1, "", str(e)

if __name__ == '__main__':

    console.clear()

#-- System check  -------------------------------------------------------------

    check_sudo()

    if not SYSTEM_CPU:  SYSTEM_CPU  = get_cpu_brand()
    if not SYSTEM_GPU:  SYSTEM_GPU  = get_graphics_card_brand()
    if not SYSTEM_VIRT: SYSTEM_VIRT = get_virtualizer().capitalize()

#-- User input ----------------------------------------------------------------

    console.print(Rule("User selections for installation"), style='success')

    # Get installation variables
    if not DRIVE: DRIVE = select_drive()
    if not USER_NAME: USER_NAME = select_username()
    if not USER_PASSWORD: USER_PASSWORD = select_password('User', min_length=3)
    if not LUKS_PASSWORD: LUKS_PASSWORD = select_password('Luks', min_length=3)
    if not SYSTEM_LOCALE: SYSTEM_LOCALE = select_locale()
    if not SYSTEM_CHARMAP: SYSTEM_CHARMAP = select_charmap()
    if not SYSTEM_TIMEZONE: SYSTEM_TIMEZONE = select_timezone()
    if not SYSTEM_COUNTRY: SYSTEM_COUNTRY, SYSTEM_COUNTRY_CODE = select_country()

#-- User validation --------------------------------------------------------

    console.print(Rule("Installation selections"), style='success')

    if SYSTEM_CPU:
        console.print(f'CPU .................: [green]{SYSTEM_CPU}[/]', style='info')
    else:
        console.print('CPU not detected', style='critical')

    if SYSTEM_GPU:
        console.print(f'GPU .................: [green]{SYSTEM_GPU}[/]', style='info')
    else:
        console.print('GPU not detected', style='critical')

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

    if SYSTEM_LOCALE:
        console.print(f'Selected locale .....: [green]{SYSTEM_LOCALE}[/]', style='info')
    else:
        console.print('No locale selected.', style='critical')

    if SYSTEM_CHARMAP:
        console.print(f'Selected charmap ....: [green]{SYSTEM_CHARMAP}[/]', style='info')
    else:
        console.print('No charmap selected.', style='critical')

    if SYSTEM_TIMEZONE:
        console.print(f'Selected timezone....: [green]{SYSTEM_TIMEZONE}[/]', style='info')
    else:
        console.print('No timezone selected.', style='critical')

    if SYSTEM_COUNTRY:
        console.print(f'Selected country ....: [green]{SYSTEM_COUNTRY}[/]', style='info')
        console.print(f'Selected country code: [green]{SYSTEM_COUNTRY_CODE}[/]', style='info')
    else:
        console.print('No country selected.', style='critical')

    if Prompt.ask('\nAre these selections correct, and continue installation?', choices=['y', 'n']) == 'n':
        exit()

#-- System Preparation and Checks  -----------------------------------------

    # run_bash('Get local mirrors', 'reflector --country {SYSTEM_COUNTRY} --latest 10 --sort rate --save /etc/pacman.d/mirrorlist')

#-- Disk Partitioning, Formatting and Mounting  ---------------------------

    console.print(Rule("Partitioning, Encrypting and Formatting"), style='success')

    # Write random data to the whole disk
    if not DEBUG: run_bash('Disk - Write random data to disk', 'dd=1M if=/dev/urandom of={DRIVE} || true')
    if not DEBUG: run_bash('Disk - Remove file system bytes','lsblk -plnx size -o name {DISK} | xargs -n1 wipefs --all')

    # Create partition table and name partitions
    run_bash('Partitioning - Create partition table', 'sgdisk --clear {DRIVE} --new 1::-551MiB --new 2::0 --typecode 2:ef00 {DRIVE}')
    run_bash('Partitioning - Name the partitions', 'sgdisk {DRIVE} --change-name=1:{PART_1_NAME} --change-name=2:{PART_2_NAME}')

    # Format partitions
    # -- partition 2 - Root  ---------------------------------------------------
    run_bash('Partition 2 - Formatting {PART_2_NAME}','mkfs.vfat -n {PART_2_NAME} -F 32 {DRIVE}2')
    run_bash('Partition 2 - Get UUID for {PART_2_NAME}', 'lsblk -o uuid {DRIVE}2 | tail -1', output_var='PART_2_UUID')

##- partition 1 ----------------------------------------------------------

    run_bash('Partition 1 - Encrypting {PART_1_NAME}','cryptsetup luksFormat -q --type luks1 --label {PART_1_NAME} {DRIVE}1',input="{LUKS_PASSWORD}")
    run_bash('Partition 1 - Get UUID for {PART_1_NAME}', 'cryptsetup luksUUID {DRIVE}1', output_var='PART_1_UUID')
    run_bash('Partition 1 - Open {PART_1_NAME}', 'cryptsetup luksOpen {DRIVE}1 {PART_1_UUID}' ,input="{LUKS_PASSWORD}")

    run_bash('Partition 1 - Set file system {PART_1_NAME} to BTRFS', 'mkfs.btrfs --label {PART_1_NAME} /dev/mapper/{PART_1_UUID}')
    run_bash('Partition 1 - Mount {PART_1_NAME}', 'mount /dev/mapper/{PART_1_UUID} /mnt')
    run_bash('Partition 1 - Create subvolume @',                   'btrfs subvolume create /mnt/@')
    run_bash('Partition 1 - Create subvolume @home',               'btrfs subvolume create /mnt/@home')
    run_bash('Partition 1 - Create subvolume @swap',               'btrfs subvolume create /mnt/@swap')
    run_bash('Partition 1 - Create subvolume @snapshots',          'btrfs subvolume create /mnt/@snapshots')
    run_bash('Partition 1 - Create subvolume @home-snapshots',     'btrfs subvolume create /mnt/@home-snapshots')
    run_bash('Partition 1 - Create subvolume @libvirt',            'btrfs subvolume create /mnt/@libvirt')
    run_bash('Partition 1 - Create subvolume @docker',             'btrfs subvolume create /mnt/@docker')
    run_bash('Partition 1 - Create subvolume @cache-pacman-pkgs',  'btrfs subvolume create /mnt/@cache-pacman-pkgs')
    run_bash('Partition 1 - Create subvolume @var',                'btrfs subvolume create /mnt/@var')
    run_bash('Partition 1 - Create subvolume @var-log',            'btrfs subvolume create /mnt/@var-log')
    run_bash('Partition 1 - Create subvolume @var-tmp',            'btrfs subvolume create /mnt/@var-tmp')
    run_bash('Partition 1 - Umount {PART_1_NAME}', 'umount /mnt')

    # Copy-on-Write is not good for big files that are written multiple times.
    # This includes: logs, containers, virtual machines, databases, etc.
    # They usually lie in /var, therefore CoW will be disabled for everything in /var
    # Note that currently btrfs does not support the nodatacow mount option.
    run_bash('Partition 1 - Mount @',                  'mount         -o subvol=@,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt')
    run_bash('Partition 1 - Mount @home',              'mount --mkdir -o subvol=@home,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/home')
    run_bash('Partition 1 - Mount @swap',              'mount --mkdir -o subvol=@swap,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/.swap')
    run_bash('Partition 1 - Mount @snaphots',          'mount --mkdir -o subvol=@snapshots,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/.snapshots')
    run_bash('Partition 1 - Mount @home-snapshots',    'mount --mkdir -o subvol=@home-snapshots,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/home/.snaphots')
    run_bash('Partition 1 - Mount @var',               'mount --mkdir -o subvol=@var,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/var')
    run_bash('Partition 1 - Mount @var-log',           'mount --mkdir -o subvol=@var-log,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/var/log')
    run_bash('Partition 1 - Mount @var-tmp',           'mount --mkdir -o subvol=@var-tmp,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/var/tmp')
    run_bash('Partition 1 - Mount @libvirt',           'mount --mkdir -o subvol=@libvirt,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/lib/libvirt')
    run_bash('Partition 1 - Mount @docker',            'mount --mkdir -o subvol=@docker,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/lib/docker')
    run_bash('Partition 1 - Mount @cache-pacman-pkgs', 'mount --mkdir -o subvol=@cache-pacman-pkgs,{BTRFS_MOUNT_OPT} /dev/mapper/{PART_1_UUID} /mnt/cache/pacman/pkgs')
    run_bash('Partition 1 - Disable CoW on /var/',  'chattr +C /mnt/var')
    Prompt.ask('Wait here')

##- partition 2 ---------------------------------------------------------------

    run_bash('Partition 2 - Mount "/mnt/efi"',         'mount --mkdir -o umask=0077 {DRIVE}2 /mnt/efi')

##- swap file -----------------------------------------------------------------

    run_bash('Swapfile creation','btrfs filesystem mkswapfile /mnt/.swap/swapfile')
    run_bash('Swapfile make','mkswap /mnt/.swap/swapfile')
    run_bash('Swapfile on','swapon /mnt/.swap/swapfile')

#-- Software Installation  ----------------------------------------------------

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
    run_bash('Installing base packages', 'pacstrap -K /mnt {SYSTEM_PKGS}')

#-- Copy config files  --------------------------------------------------------

    copy_file_structure('rootfs', '/mnt')

#-- Patch config files  --------------------------------------------------------

    run_bash('Copy mirror list', 'cp /etc/pacman.d/mirrorlist /mnt/etc/pacman.d/')
    run_bash('Patch pacman configuration -colours', 'sed -i "s/#Color/Color/g" /mnt/etc/pacman.conf')
    run_bash('Patch qemu configuration - user', 'sed -i "s/username_placeholder/$user/g" /mnt/etc/libvirt/qemu.conf')
    run_bash('Patch tty configuration - user', 'sed -i "s/username_placeholder/$user/g" /mnt/etc/systemd/system/getty@tty1.service.d/autologin.conf')
    run_bash('Patch shell - dash', 'ln -sfT dash /mnt/usr/bin/sh')

#-- Write Kernel Command Line  ------------------------------------------------

    # Note: Erwin cryptedevice :UUID or archlinux?
    SYSTEM_CMD = [
        'lsm=landlock,lockdown,yama,integrity,apparmor,bpf', # Customize Linux Security Modules to include AppArmor
        'lockdown=integrity',                                # Put kernel in integrity lockdown mode
        f'cryptdevice={PART_1_NAME}:{PART_1_UUID}',          # The LUKS device to decrypt
        f'root=/dev/mapper/{PART_1_UUID}',                   # The decrypted device to mount as the root
        'rootflags=subvol=@',                                # Mount the @ btrfs subvolume inside the decrypted device as the root
        'mem_sleep_default=deep',                            # Allow suspend state (puts device into sleep but keeps powering the RAM for fast sleep mode recovery)
        'audit=1',                                           # Ensure that all processes that run before the audit daemon starts are marked as auditable by the kernel
        'audit_backlog_limit=32768',                         # Increase default log size
        'quiet splash rd.udev.log_level=3'                   # Completely quiet the boot process to display some eye candy using plymouth instead :)
    ]

    with open('test.txt', 'a') as f:
        f.write(' '.join(SYSTEM_CMD) + '\n')


# -- Cleaning up --------------------------------------------------------------
    run_bash('Partition X - Umount', 'umount --recursive /mnt')
    run_bash('Partition 1 - Close {PART_1_UUID}', 'cryptsetup luksClose {PART_1_UUID}')
