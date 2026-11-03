#!/bin/sh
# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
studio_source=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
studio_build=${1:?Usage: build_macos.sh ABSOLUTE_BUILD_DIRECTORY ABSOLUTE_INSTALL_DIRECTORY}
studio_install=${2:?Absolute install directory required}
case "$studio_build:$studio_install" in /*:/*) ;; *) echo 'Absolute output paths required' >&2; exit 2;; esac
cmake -S "$studio_source" -B "$studio_build" -G Ninja -C "$studio_source/finalverse/studio_s0.cmake" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$studio_install"
cmake --build "$studio_build" --target install --parallel "${STUDIO_BUILD_JOBS:-4}"
