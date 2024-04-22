#!/usr/bin/env bash
#shellcheck disable=SC2034
#SC2034: foo appears unused. Verify it or export it.
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

GITHUB_USER="echjansen"
BRANCH="sid"
HASH=""
ARTIFACT="pure-arch-${BRANCH}"

while getopts "b:h:u:" arg; do
  case ${arg} in
    b)
      BRANCH="${OPTARG}"
      ARTIFACT="pure-arch-${BRANCH}"
      ;;
    h)
      HASH="${OPTARG}"
      ARTIFACT="pure-arch-${HASH}"
      ;;
    u)
      GITHUB_USER=${OPTARG}
      ;;
    ?)
      echo "Invalid option: -${OPTARG}."
      exit 1
      ;;
  esac
done

set -o xtrace
if [ -n "$HASH" ]; then
  curl -sL -o "${ARTIFACT}.zip" "https://github.com/${GITHUB_USER}/pure-arch/archive/${HASH}.zip"
  bsdtar -x -f "${ARTIFACT}.zip"
  cp -R "${ARTIFACT}"/*.sh "${ARTIFACT}"/*.conf "${ARTIFACT}"/files/ "${ARTIFACT}"/configs/ ./
else
  curl -sL -o "${ARTIFACT}.zip" "https://github.com/${GITHUB_USER}/pure-arch/archive/refs/heads/${BRANCH}.zip"
  bsdtar -x -f "${ARTIFACT}.zip"
  cp -R "${ARTIFACT}"/*.sh "${ARTIFACT}"/*.conf "${ARTIFACT}"/files/ "${ARTIFACT}"/configs/ ./
fi
chmod +x configs/*.sh
chmod +x ./*.sh
