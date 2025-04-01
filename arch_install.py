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
import subprocess
from typing import List
from rich.console import Console
from rich.theme import Theme
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table


theme = Theme({
    'info':     'yellow',
    'warning':  'bold yellow',
    'success':  'green',
    'error':    'red',
    'critical': 'bold reverse red',
    'debug':    'blue',
})

console = Console(theme=theme)
prompt = Prompt()
# table_devices = table.Table(title='Available Drives')
# table_locale = table.Table(title="Matching Locales")

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
                    '[bold yellow]Enter the index of the drive to select[/]',
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

def get_password(user_prompt: str, min_length: int = 8) -> str:
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
        password = prompt.ask(f'[bold yellow]Enter the password for {user_prompt} (minimum {min_length} characters)[/]', password=True)
        if len(password) < min_length:
            console.print(f'Password must be at least {min_length} characters long. Please try again.', style='error')
            continue

        password_confirmation = prompt.ask(f'[bold yellow]Confirm the password for {user_prompt}[/]', password=True)

        if password == password_confirmation:
            return password
        else:
            console.print('Passwords do not match. Please try again.', style='error')

def get_username() -> str:
    '''
    Prompts the user to enter a username. The username cannot be empty.
    it continues prompting until a non-empty username is provided.

    Returns:
        str: The entered username.
    '''
    while True:
        username = prompt.ask('[bold yellow]Enter username[/]')

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
            search_term = prompt.ask(f"[bold yellow]Enter search term for {item_type} (or press Enter to list all):[/]")

            filtered_items = filter_items(all_items, search_term) if search_term else all_items

            if not filtered_items:
                console.print("[bold red]No matching items found. Please try again.[/]")
                continue

            table = Table(title=f"Available {item_type.capitalize()}s")
            table.add_column("Index", justify="right", style="cyan", no_wrap=True)
            table.add_column(item_type.capitalize(), style="magenta")

            display_items = [os.path.splitext(item)[0] for item in filter_items] if remove_extension else filtered_items

            for i, item in enumerate(display_items):
                table.add_row(str(i + 1), item)

            console.print(table)

            selection = prompt.ask(f"[bold yellow]Enter the index of the {item_type} to select (or press Enter to search again):[/]", default="", show_default=False)

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
    return select_from_directory_with_search("/usr/share/i18n/locales", "Language")


def select_charmap() -> str:
    """
    Lists and allows the user to select a charmap from /usr/share/i18n/charmaps, with a search function.

    Returns:
        str: The selected charmap name (e.g., "UTF-8").
             Returns an empty string if no charmap is selected or an error occurs.
    """
    return select_from_directory_with_search("/usr/share/i18n/charmaps", "Character Map", remove_extension=True)


if __name__ == '__main__':

    console.clear()

    #-- User input ------------------------------------------------------------
    console.print(Rule("User selections for installation"))

    # Get installation variables
    drive = select_drive()
    username = get_username()
    userpass = get_password('Luks', min_length=3)
    locale = select_locale()
    charmap = select_charmap()

    if drive:
        console.print(f'Selected drive: [yellow]{drive}[/]', style='success')
    else:
        console.print('No drive selected.', style='critical')

    if username:
        console.print(f'Selected username: [yellow]{username}[/]', style='success')
    else:
        console.print('No username selected.', style='critical')

    if locale:
        console.print(f'Selected locale: [yellow]{locale}[/]', style='success')
    else:
        console.print('No locale selected.', style='critical')

#    if charmap:
        console.print(f'Selected charmap: [yellow]{charmap}[/]', style='success')
#    else:
#        console.print('No charmap selected.', style='critical')

    if Prompt.ask('Are these selections correct, and continue installation?', choices=['y', 'n']) == 'n':
        exit()
