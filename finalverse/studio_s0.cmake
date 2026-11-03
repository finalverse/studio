# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
# Bounded Apple Silicon development profile. Eevee, modeling, Python, GLB and Metal.
# Heavy optional production codecs/renderers remain available in upstream profiles.
include("${CMAKE_CURRENT_LIST_DIR}/../build_files/cmake/config/blender_lite.cmake")
set(WITH_BUILDINFO ON CACHE BOOL "" FORCE)
set(WITH_ASSERT_RELEASE OFF CACHE BOOL "" FORCE)
set(WITH_PYTHON_INSTALL ON CACHE BOOL "" FORCE)
set(WITH_VULKAN_BACKEND OFF CACHE BOOL "" FORCE)
set(WITH_GTESTS OFF CACHE BOOL "" FORCE)
set(CPACK_OVERRIDE_PACKAGENAME "finalverse-studio-s0" CACHE STRING "" FORCE)
