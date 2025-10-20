# === P U R E - A R C H ===
A security focused  Arch Linux Operating System installer using python.

## Highlights
- [ ] **systemd** focused
- [ ] **btrfs** file system
- [ ] **luks** (luks2) disk enxryption
- [ ] **no boot-loader** like *grub*, *systemd_boot*, with **Unified Kernel Images**
- [ ] **secure boot** without Microsoft keys
- [ ] **configurable** with a toml configurations file
- [ ] **hardened** (optional) with configuration files
- [ ] **strict firewall rules**

## Installation

### Requirements
- Latest live Arch Linux ISO
- A hard drive of 15GB

### Installation instructions:
```bash
pacman -Sy                                        # Update the Arch keyring
pacman -S git                                     # Install git
git clone https://github.com/echjansen/pure-arch  # Get this repository
cd pure-arch
python -m main
```

> [!CAUTION]
> The installation will wipe your selected installation drive. Be carefull!

### Project Structure
pure_arch/
├── pure_arch/                # The primary source code package (importable)
│   ├── __init__.py           # Makes 'my_app' a Python package
│   ├── main.py               # Entry point, CLI setup, or application bootstrap
│   ├── core/                 # Sub-package for core business logic/classes
│   │   ├── __init__.py
│   │   ├── firstboot.py      # System setup
│   │   ├── disk.py           # Wipe, Format, mount, umout etc,
│   │   ├── packages.py       #
│   │   ├── chroot.py         #
│   │   ├── file.py           #
│   │   ├── services.py       #
│   │   ├── users.py          #
│   │   └── bootloader.py     #
│   ├── cli.py                # Optional: Logic for Command Line Interface (CLI)
│   └── utils.py              # Utility functions (e.g., file handling, date formatting)
├── tests/                    # Directory for all tests
│   ├── conftest.py           # Shared fixtures/config for pytest
│   ├── unit/                 # Unit tests (e.g., testing individual classes/functions)
│   │   └── test_calculator.py
│   └── integration/          # Integration tests (e.g., testing multiple components interacting)
│       └── test_db_connection.py
├── scripts/                  # Helper scripts (e.g., deployment, database migrations)
│   └── setup_env.sh
├── .gitignore                # Specifies files/directories to ignore in Git
├── README.md                 # Project documentation and setup instructions
├── pyproject.toml            # Modern configuration file (recommended over setup.cfg)
├── requirements.txt          # For simple projects OR for environment-specific dependencies
└── .env.example              # Template for environment variables (for security)

### Dependencies
Note that the following dependencies need to be installed prior to running pure-arch:
- pydantic                      # Configuration parser and validator
- typer                         # Modern looking CLI
