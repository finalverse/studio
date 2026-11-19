# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
# V1 profile: the S0 development profile plus the geometry features V1 character
# work needs (octree Remesh, OpenSubdiv). The S0 "lite" base disables them, which made Remesh and Subdivision
# Surface silent no-ops in S0–S2 builds.
include("${CMAKE_CURRENT_LIST_DIR}/studio_s0.cmake")
set(WITH_MOD_REMESH ON CACHE BOOL "" FORCE)
set(WITH_OPENSUBDIV ON CACHE BOOL "" FORCE)
# OpenVDB stays off: its pinned libraries are unfetched Git LFS pointers here.
# Octree "smooth" remesh needs only WITH_MOD_REMESH.
set(WITH_OPENVDB OFF CACHE BOOL "" FORCE)
set(CPACK_OVERRIDE_PACKAGENAME "finalverse-studio-v1" CACHE STRING "" FORCE)
