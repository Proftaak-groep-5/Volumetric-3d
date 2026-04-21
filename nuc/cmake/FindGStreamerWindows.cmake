set(GStreamerWindows_FOUND FALSE)

file(GLOB _gst_program_files
    LIST_DIRECTORIES TRUE
    "C:/gstreamer/*/msvc_x86_64"
    "C:/Program Files/gstreamer/*/msvc_x86_64"
    "C:/Program Files/GStreamer/*/msvc_x86_64")

set(_gst_hints
    "$ENV{GSTREAMER_ROOT_DIR}"
    "$ENV{GSTREAMER_1_0_ROOT_MSVC_X86_64}"
    "$ENV{GSTREAMER_1_0_ROOT_X86_64}"
    "C:/gstreamer/1.0/msvc_x86_64"
    "C:/Program Files/gstreamer/1.0/msvc_x86_64"
    ${_gst_program_files})

find_path(GStreamerWindows_INCLUDE_DIR
    NAMES gst/gst.h
    PATH_SUFFIXES include/gstreamer-1.0
    HINTS ${_gst_hints})

find_path(GStreamerWindows_GLIB_INCLUDE_DIR
    NAMES glib.h
    PATH_SUFFIXES include/glib-2.0
    HINTS ${_gst_hints})

find_path(GStreamerWindows_GLIB_CONFIG_INCLUDE_DIR
    NAMES glibconfig.h
    PATH_SUFFIXES lib/glib-2.0/include
    HINTS ${_gst_hints})

find_library(GStreamerWindows_GSTREAMER_LIBRARY
    NAMES gstreamer-1.0
    PATH_SUFFIXES lib
    HINTS ${_gst_hints})
find_library(GStreamerWindows_GSTAPP_LIBRARY
    NAMES gstapp-1.0
    PATH_SUFFIXES lib
    HINTS ${_gst_hints})
find_library(GStreamerWindows_GSTBASE_LIBRARY
    NAMES gstbase-1.0
    PATH_SUFFIXES lib
    HINTS ${_gst_hints})
find_library(GStreamerWindows_GSTVIDEO_LIBRARY
    NAMES gstvideo-1.0
    PATH_SUFFIXES lib
    HINTS ${_gst_hints})
find_library(GStreamerWindows_GOBJECT_LIBRARY
    NAMES gobject-2.0
    PATH_SUFFIXES lib
    HINTS ${_gst_hints})
find_library(GStreamerWindows_GLIB_LIBRARY
    NAMES glib-2.0
    PATH_SUFFIXES lib
    HINTS ${_gst_hints})
find_path(GStreamerWindows_PLUGIN_DIR
    NAMES coreelements.dll
    PATH_SUFFIXES lib/gstreamer-1.0
    HINTS ${_gst_hints})

string(REPLACE ";" "\n  - " GStreamerWindows_SEARCH_HINTS "${_gst_hints}")

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(GStreamerWindows
    REQUIRED_VARS
        GStreamerWindows_INCLUDE_DIR
        GStreamerWindows_GLIB_INCLUDE_DIR
        GStreamerWindows_GLIB_CONFIG_INCLUDE_DIR
        GStreamerWindows_GSTREAMER_LIBRARY
        GStreamerWindows_GSTAPP_LIBRARY
        GStreamerWindows_GSTBASE_LIBRARY
        GStreamerWindows_GSTVIDEO_LIBRARY
        GStreamerWindows_GOBJECT_LIBRARY
        GStreamerWindows_GLIB_LIBRARY)

if(GStreamerWindows_FOUND)
    set(GStreamerWindows_INCLUDE_DIRS
        ${GStreamerWindows_INCLUDE_DIR}
        ${GStreamerWindows_GLIB_INCLUDE_DIR}
        ${GStreamerWindows_GLIB_CONFIG_INCLUDE_DIR})
    set(GStreamerWindows_LIBRARIES
        ${GStreamerWindows_GSTREAMER_LIBRARY}
        ${GStreamerWindows_GSTAPP_LIBRARY}
        ${GStreamerWindows_GSTBASE_LIBRARY}
        ${GStreamerWindows_GSTVIDEO_LIBRARY}
        ${GStreamerWindows_GOBJECT_LIBRARY}
        ${GStreamerWindows_GLIB_LIBRARY})
endif()
