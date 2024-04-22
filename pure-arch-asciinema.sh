#!/usr/bin/env bash
set -eu

# Copyright (C) 2024 echjansen

# This file is part of = P U R E - A R C H =

# pure-arch is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or (at
# your option) any later version.

# pure-arch is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with pure-emacs.  If not, see <http://www.gnu.org/licenses/>.

# Pure Arch installs an Arch Linux operating system
# unattended, automated, customized and secured.

#curl -L -o asciinema-2.0.2.zip https://github.com/asciinema/asciinema/archive/v2.0.2.zip
#bsdtar xvf asciinema-2.0.2.zip
#rm -f pure-arch.asciinema
#(cd asciinema-2.0.2 && python3 -m asciinema rec --stdin -i 5 ~/pure-arch.asciinema)

rm -f pure-arch.asciinema

pacman -Sy
pacman -S --noconfirm asciinema

clear
asciinema rec --stdin -i 5 ~/pure-arch.asciinema
