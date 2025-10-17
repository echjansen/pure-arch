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
