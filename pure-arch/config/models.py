# pure_arch/config/models.py

import tomlkit
import typer
from pydantic import BaseModel, Field, SecretStr, conlist, computed_field
from typing import List, Optional, Union, Literal, Set, Tuple, Any
from pathlib import Path

# --- 1. Sub-Models ---

# System Configuration
class Host(BaseModel):
    """General system properties."""
    system: Literal["auto", "baremetal", "oracle", "vmware", "kvm"]
    cpu: Literal["auto", "intel", "amd", "none"]
    gpu: Literal["auto", "nvidia", "amd", "intel"]
    opensource: bool

# Partition Configuration
class Partition(BaseModel):
    """Configuration for a single disk partition."""
    number: int = Field(ge=1, description="Partition number.")
    label: str
    type: str
    size: str

    start: Optional[str] = Field("0")
    path: Optional[str] = Field(None)
    guid: Optional[str] = Field(None)

    filesystem: Literal["fat32", "vfat", "ext4", "btrfs", "xfs", "f2fs"]
    crypt: bool

    # Encryption Fields
    crypttype: Optional[Literal["luks1", "luks2"]] = Field("luks2")
    cryptname: Optional[str] = Field(None)
    cryptlabel: Optional[str] = Field(None)

    # Btrfs Fields
    btrfsoptions: Optional[str] = Field(None)
    btrfssubvolumes: Optional[List[str]] = Field(None)

# Disk Configuration
class Disk(BaseModel):
    """Configuration for a single physical disk."""
    path: str
    wipe: bool
    type: Literal["GPT", "MBR"]
    partition: conlist(Partition, min_length=1)

# Linux Configuration
class Linux(BaseModel):
    """General Linux environment and package configuration."""
    packages: List[str]
    services: Optional[List[List[str]]] = Field(None) # e.g., [['enable', 'sshd']]
    groups: Optional[List[str]] = Field(None)

# Firstboot Configuration
class Firstboot(BaseModel):
    """Parameters for initial system setup."""
    systemd: bool
    locale: str
    timezone: str
    hostname: str
    keyboard: str
    packages: Optional[List[str]] = Field(None)

# User Configuration
class User(BaseModel):
    """Configuration for a user account."""
    name: str
    homed: bool
    password: SecretStr
    groups: Optional[List[str]] = Field(None)
    services: Optional[List[List[str]]] = Field(None)
    files: Optional[List[List[Union[str, List[str]]]]] = Field(None) # Complex structure for file operations
    packages: Optional[List[str]] = Field(None)

# Application Configuration
class Application(BaseModel):
    """Defines command execution and file operations for a specific application/step."""
    name: str
    commands: Optional[List[List[str]]] = Field(None)
    files: Optional[List[List[Union[str, List[str]]]]] = Field(None) # Complex structure for file operations

# Bootloader Configuration
class Bootloader(BaseModel):
    """Configuration for bootloader installation."""
    type: Literal["grub", "systemd-boot"]
    efi_partition: str
    root_partition: str
    grub_partition: Optional[str] = Field(None)
    packages: Optional[List[str]] = Field(None)

# --- 2. Top-Level Root Model ---

# Define the complex types for clarity
ServiceList = List[Tuple[str, str]] # Example: [["enable", "sshd"]]
CommandList = List[List[str]]       # Example: [["mkdir", "-p", "/mnt/efi/EFI/Linux"]]
FileList = List[List[Union[str, List[str]]]] # Example: [["uncomment-line", "%wheel ALL=", "/etc/sudoers"]]

class ArchInstallerConfig(BaseModel):
    """The top-level configuration model representing the entire config.toml file."""

    host: 'Host'
    disk: conlist('Disk', min_length=1)
    linux: 'Linux'
    firstboot: 'Firstboot'
    bootloader: 'Bootloader'
    user: List['User']
    application: List['Application']

    def _recursive_extract(self, data: Any, field_name: str) -> List[Any]:
        """
        Recursively extracts all lists associated with a given field_name
        from dictionaries and lists within the configuration data.

        NOTE: This function must handle Pydantic objects or plain dicts/lists.
        """
        results: List[Any] = []

        # Convert Pydantic model instances to their raw dictionary form
        if isinstance(data, BaseModel):
            data = data.__dict__

        if isinstance(data, dict):
            for key, value in data.items():
                if key == field_name and isinstance(value, list):
                    # Found the target field (e.g., 'packages': [...])
                    results.extend(value)
                else:
                    # Recurse into the value
                    results.extend(self._recursive_extract(value, field_name))

        elif isinstance(data, list):
            # Recurse into each item in the list
            for item in data:
                results.extend(self._recursive_extract(item, field_name))

        # Handle SecretStr objects correctly, as they don't recursively dump their value well
        # This is implicitly handled by the Pydantic serialization if we use the right entry point.

        return results

    def _extract_field_from_model(self, field_name: str, unique: bool = False) -> Union[List[str], List, List[Tuple[str, str]]]:
        """
        Public method to initiate recursive extraction using the raw model data.
        """
        # The extractor will use the internal __dict__ or model_dump() safely
        # based on the BaseModel check within the recursion.
        raw_results = self._recursive_extract(self, field_name)

        if unique:
            # SecretStr values are extracted as SecretStr objects, so we need to
            # convert them to strings before adding them to the set.
            # However, for packages/groups, they are already strings.
            return sorted(list(set(raw_results)))

        return raw_results

    @computed_field
    @property
    def all_packages(self) -> List[str]:
        """Gathers all unique packages defined across all sections."""
        return self._extract_field_from_model('packages', unique=True)

    @computed_field
    @property
    def all_groups(self) -> List[str]:
        """Gathers all unique groups required by the system and users."""
        return self._extract_field_from_model('groups', unique=True)

    @computed_field
    @property
    def all_services(self) -> ServiceList:
        """Gathers all services to be enabled/managed across all sections."""
        return self._extract_field_from_model('services', unique=False)

    @computed_field
    @property
    def all_commands(self) -> CommandList:
        """Gathers all shell commands from all application steps."""
        return self._extract_field_from_model('commands', unique=False)

    @computed_field
    @property
    def all_file_operations(self) -> FileList:
        """Gathers all file operations from user and application steps."""
        return self._extract_field_from_model('files', unique=False)

    @classmethod
    def load_config_from_file(cls, path: Path) -> 'ArchInstallerConfig':
        """Loads and validates a TOML file against the Pydantic schema."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            raise ValueError(f"Error reading configuration file: {e}")

        try:
            data = tomlkit.parse(content)
        except Exception as e:
            raise ValueError(f"Invalid TOML format in file: {e}")

        # The cls(**data) call instantiates the model and runs validation
        return cls(**data)

    # Helper to safely access sensitive fields (Pydantic V2)
    def _safe_str(self, s: Optional[SecretStr]) -> str:
        """Safely accesses and truncates SecretStr value for display (Pydantic V2)."""
        if not s:
            return "N/A"

        # Pydantic V2: Use .get_secret_value() to get the raw string
        secret_value = s.get_secret_value()

        if secret_value:
            # Truncate the string for display
            return secret_value[:4] + "..."

        return "N/A"

    def display_summary(self) -> str:
        """Generates the initial summary (General, Disk, User Details)."""
        s = typer.style("\nGENERAL CONFIGURATION SUMMARY", fg=typer.colors.BLUE, bold=True) + "\n"
        s += "----------------------------------------\n"
        s += f"  Hostname:           {self.firstboot.hostname}\n"
        s += f"  OS Type:            {self.host.system} ({'Open Source' if self.host.opensource else 'Proprietary'}) | CPU: {self.host.cpu}\n"
        s += f"  Timezone:           {self.firstboot.timezone}\n"
        s += f"  Bootloader:         {self.bootloader.type} (on {self.bootloader.efi_partition})\n"
        s += f"  Users to Create:    {len(self.user)}\n"

        # --- Disk Summary ---
        s += typer.style("\nDISK & PARTITION PLAN", fg=typer.colors.BLUE, bold=True) + "\n"
        s += "----------------------------------------\n"
        for i, disk in enumerate(self.disk):
            disk_action = typer.style("WIPING", fg=typer.colors.RED) if disk.wipe else "Keeping"
            s += f"[{i+1}] Device: {typer.style(disk.path, fg=typer.colors.CYAN)} ({disk.type}, {disk_action})\n"
            for j, p in enumerate(disk.partition):
                crypt_status = typer.style(f"LUKS ({p.crypttype})", fg=typer.colors.YELLOW) if p.crypt else ""
                s += f"  - P{p.number}: {p.label:<10} ({p.size:<5}) -> FS: {p.filesystem:<5} Mount: {p.path:<10} {crypt_status}\n"
                if p.filesystem == "btrfs" and p.btrfssubvolumes:
                    s += f"    ╰─ {typer.style('Btrfs Subvolumes', bold=True)} ({len(p.btrfssubvolumes)} total):\n"
                    for subvol in p.btrfssubvolumes: s += f"       • {subvol}\n"

        # --- User Details ---
        s += typer.style("\nUSER DETAILS", fg=typer.colors.BLUE, bold=True) + "\n"
        s += "----------------------------------------\n"
        for user in self.user:
            s += f"  👤 User '{user.name}': Homed={user.homed}, Groups={', '.join(user.groups or ['None'])}, Pwd={self._safe_str(user.password)}\n"

        return s

    def display_actions(self) -> str:
        """Generates the consolidated instructions (Packages, Services, Commands, Files)."""
        s = ""
        s += typer.style("\nCONSOLIDATED INSTALLATION ACTIONS", fg=typer.colors.BLUE, bold=True) + "\n"
        s += "----------------------------------------\n"

        # 1. Packages
        s += f"  📦 {typer.style('Total Unique Packages:', bold=True)} {len(self.all_packages)}\n"
        s += f"    {', '.join(self.all_packages)}\n"

        # 2. Services
        s += f"  ⚙️ {typer.style('Services to Manage:', bold=True)} {len(self.all_services)}\n"
        for status, service in self.all_services:
            color = typer.colors.GREEN if status == "enable" else typer.colors.YELLOW
            s += f"    - {typer.style(status.upper(), fg=color)}: {service}\n"

        # 3. Groups
        s += f"  👥 {typer.style('Required Groups:', bold=True)} {len(self.all_groups)}\n"
        s += "    " + ', '.join(self.all_groups) + "\n"

        # 4. Commands
        s += f"  💻 {typer.style('Shell Commands:', bold=True)} {len(self.all_commands)}\n"
        for i, cmd in enumerate(self.all_commands):
            s += f"    - {i+1}: {typer.style(' '.join(cmd), fg=typer.colors.BRIGHT_WHITE)}\n"

        # 5. File Operations
        s += f"  📝 {typer.style('File Operations:', bold=True)} {len(self.all_file_operations)}\n"
        for i, file_op in enumerate(self.all_file_operations):
            op = file_op[0]
            target = file_op[-1]
            s += f"    - {i+1}: {op.upper()} on {target}\n"

        return s
