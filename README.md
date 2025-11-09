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

### Usage

Depending on the level of experience, this pure-arch installation script can be used in different ways:

For the beginner, use a TUI that asks all required questions:

```bash
./pure-arch-install.sh

For the expert, fill out the provided pure-arch.config and run:

```bash
./pure-arch.sh --config <CONFIG.FILE>

Other arguments available:
--config <CONFIG-FILE>    - Apply values for configuration variables from config file.
--dry-run                 - Do no execute any bash shell commands. No installation.
--verbose                 - See output from each bash shell commands.
