#----------------------------------------------------------------------------------------------------------------------
# Goals:
# - Use python script to install Arch Linux
#----------------------------------------------------------------------------------------------------------------------
# Todos:
# - [ ]
# - [ ]
# - [ ]
# - [ ]
#----------------------------------------------------------------------------------------------------------------------

import os
import logging
import subprocess
from typing import List
from rich.console import Console
from rich.theme import Theme
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table


# 'rich' objects
theme = Theme({
    'info':     'yellow',
    'warning':  'bold yellow',
    'success':  'green',
    'error':    'red',
    'critical': 'bold reverse red',
    'debug':    'blue',
})

console = Console(theme=theme)
prompt  = Prompt()
log     = logging.getLogger("rich")

# Debugging variables
DEBUG = True                    # If True, report on command during execution
STEP = False                    # If true, step one command at the time

# Global Constants
PART_NAME_1 = "README"
PART_NAME_2 = "EFI"
PART_NAME_3 = "LINUX_ENCRYPTED"
PART_NAME_4 = "STORAGE_ENCRYPTED"
PART_FORMAT_4 = "BTRFS"
LINUX_ENV = "LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 KEYMAP=us DEBIAN_FRONTEND=noninteractive TERM=xterm-color"
LINUX_PKGS = "linux-image-amd64 firmware-linux firmware-iwlwifi zstd grub-efi cryptsetup cryptsetup-initramfs btrfs-progs fdisk gdisk sudo network-manager xserver-xorg xinit lightdm xfce4 dbus-x11 thunar xfce4-terminal firefox-esr keepassxc network-manager-gnome mg"

# Global Variables
DRIVE = None                    # The device that will be made into a backup device
DRIVE_PASSWORD = None           # Encryption password for partitions
UUID_PART1 = None               # UUID of partition 1
UUID_PART2 = None               # UUID of partition 2
UUID_PART3 = None               # UUID of partition 3
UUID_PART4 = None               # UUID of partition 4
USER_NAME = None                # User name for backup devices (no root)
USER_PASSWORD = None            # User password for backup device
LUKS_PASSWORD = None            # Luks password for drive(s)
SYSTEM_LOCALE = None            # System locale ('en_US')
SYSTEM_CHARMAP = None           # System keyboard layout ('UTF-8')

# Deleteme
DRIVE = '/dev/sdb'              # The device that will be made into a backup device
DRIVE_PASSWORD = '123'          # Encryption password for partitions
UUID_PART1 = None               # UUID of partition 1
UUID_PART2 = None               # UUID of partition 2
UUID_PART3 = None               # UUID of partition 3
UUID_PART4 = None               # UUID of partition 4
USER_NAME = 'echjansen'         # User name for backup devices (no root)
USER_PASSWORD = '123'           # User password for backup device
LUKS_PASSWORD = '123'           # Luks password for drive(s)
SYSTEM_LOCALE = 'en_US'         # System locale ('en_US')
SYSTEM_CHARMAP = 'UTF-8'        # System keyboard layout ('UTF-8')

#----------------------------------------------------------------------------------------------------------------------
# Supporting functions
#----------------------------------------------------------------------------------------------------------------------
def select_drive() -> str:
    """
    Prompts the user to select a drive from the available block devices.

    Uses lsblk to gather device information and Rich library for interactive
    console display and input.

    Returns:
        str: The full device name (e.g., "/dev/sda") of the selected drive.
             Returns an empty string if no valid device is selected or if an error occurs.
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
        devices = []
        for line in output.splitlines():
            parts = line.split()
            name = parts[0]
            size = parts[1]
            type = parts[2]
            mountpoint = ' '.join(parts[3:]) if len(parts) > 3 else '' # Handles missing mountpoints
            if type == 'disk':  # Only consider disks
                devices.append((name, size, mountpoint))

        if not devices:
            console.print('No available disks found.', style='error')
            return ''

        # Display the available drives in a table
        table = Table(title='Available Drives')
        table.add_column('Index', justify='center', style='success', no_wrap=True)
        table.add_column('Device Name', style='success')
        table.add_column('Size', style='success')
        table.add_column('Mountpoint', style='success')

        for i, (name, size, mountpoint) in enumerate(devices):
            table.add_row(str(i + 1), f'/dev/{name}', size, mountpoint if mountpoint != '' else '[italic]None[/]')

        console.print(table)

        # Prompt the user to select a drive
        while True:
            try:
                selection = prompt.ask(
                    '[yellow]Enter the index of the drive to select[/]',
                    default='1',
                    show_default=True
                )
                index = int(selection) - 1

                if 0 <= index < len(devices):
                    selected_device = devices[index][0]
                    return f'/dev/{selected_device}'
                else:
                    console.print('Invalid selection. Please enter a valid index.', style='error')
            except ValueError:
                console.print('Invalid input. Please enter a number.', style='error')

    except subprocess.CalledProcessError as e:
        console.print(f'Error executing lsblk: {e}', style='critical')
        return ''
    except Exception as e:
        console.print(f'An unexpected error occurred: {e}', style='critical')
        return ''

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
            table.add_column("Index", justify="right", style="cyan", no_wrap=True)
            table.add_column(item_type.capitalize(), style="magenta")

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
    logging.info(f'{description_formatted}')
    if DEBUG: log.debug(f'{command_formatted}')
    #if input: log.debug(f'Input data: {input_formatted}')

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

    #-- User input ------------------------------------------------------------
    console.print(Rule("User selections for installation"), style='success')

    # Get installation variables
    if not DRIVE: DRIVE = select_drive()
    if not USER_NAME: USER_NAME = select_username()
    if not USER_PASSWORD: USER_PASSWORD = select_password('User', min_length=3)
    if not LUKS_PASSWORD: LUKS_PASSWORD = select_password('Luks', min_length=3)
    if not SYSTEM_LOCALE: SYSTEM_LOCALE = select_locale()
    if not SYSTEM_CHARMAP: SYSTEM_CHARMAP = select_charmap()

    #-- User validation ------------------------------------------------------------
    console.print(Rule("Installation selections"), style='success')

    if DRIVE:
        console.print(f'Selected drive:     [green]{DRIVE}[/]', style='info')
    else:
        console.print('No drive selected.', style='critical')

    if USER_NAME:
        console.print(f'Selected username:  [green]{USER_NAME}[/]', style='info')
    else:
        console.print('No username selected.', style='critical')

    if SYSTEM_LOCALE:
        console.print(f'Selected locale:    [green]{SYSTEM_LOCALE}[/]', style='info')
    else:
        console.print('No locale selected.', style='critical')

    if SYSTEM_CHARMAP:
        console.print(f'Selected charmap:   [green]{SYSTEM_CHARMAP}[/]', style='info')
    else:
        console.print('No charmap selected.', style='critical')

    if Prompt.ask('\nAre these selections correct, and continue installation?', choices=['y', 'n']) == 'n':
        exit()
