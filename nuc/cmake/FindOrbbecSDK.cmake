set(OrbbecSDK_FOUND FALSE)

file(GLOB _orbbec_program_files
    LIST_DIRECTORIES TRUE
    "C:/Program Files/OrbbecSDK*"
    "C:/Program Files (x86)/OrbbecSDK*"
    "C:/OrbbecSDK*")

set(_orbbec_hints
    "$ENV{ORBBECSDK_ROOT}"
    "$ENV{ORBBEC_SDK_ROOT}"
    "C:/Program Files/OrbbecSDK"
    "C:/OrbbecSDK"
    ${_orbbec_program_files})

find_path(OrbbecSDK_INCLUDE_DIR
    NAMES libobsensor/ObSensor.hpp
    PATH_SUFFIXES include
    HINTS ${_orbbec_hints})

find_library(OrbbecSDK_LIBRARY
    NAMES OrbbecSDK obsensor
    PATH_SUFFIXES lib lib/x64
    HINTS ${_orbbec_hints})
find_file(OrbbecSDK_DLL
    NAMES OrbbecSDK.dll obsensor.dll
    PATH_SUFFIXES bin
    HINTS ${_orbbec_hints})

string(REPLACE ";" "\n  - " OrbbecSDK_SEARCH_HINTS "${_orbbec_hints}")

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(OrbbecSDK
    REQUIRED_VARS OrbbecSDK_INCLUDE_DIR OrbbecSDK_LIBRARY)

if(OrbbecSDK_FOUND AND NOT TARGET OrbbecSDK::OrbbecSDK)
    if(WIN32 AND OrbbecSDK_DLL)
        add_library(OrbbecSDK::OrbbecSDK SHARED IMPORTED)
        set_target_properties(OrbbecSDK::OrbbecSDK PROPERTIES
            IMPORTED_IMPLIB "${OrbbecSDK_LIBRARY}"
            IMPORTED_LOCATION "${OrbbecSDK_DLL}"
            INTERFACE_INCLUDE_DIRECTORIES "${OrbbecSDK_INCLUDE_DIR}")
    else()
        add_library(OrbbecSDK::OrbbecSDK UNKNOWN IMPORTED)
        set_target_properties(OrbbecSDK::OrbbecSDK PROPERTIES
            IMPORTED_LOCATION "${OrbbecSDK_LIBRARY}"
            INTERFACE_INCLUDE_DIRECTORIES "${OrbbecSDK_INCLUDE_DIR}")
    endif()
endif()

if(OrbbecSDK_FOUND AND NOT TARGET ob::OrbbecSDK)
    if(WIN32 AND OrbbecSDK_DLL)
        add_library(ob::OrbbecSDK SHARED IMPORTED)
        set_target_properties(ob::OrbbecSDK PROPERTIES
            IMPORTED_IMPLIB "${OrbbecSDK_LIBRARY}"
            IMPORTED_LOCATION "${OrbbecSDK_DLL}"
            INTERFACE_INCLUDE_DIRECTORIES "${OrbbecSDK_INCLUDE_DIR}")
    else()
        add_library(ob::OrbbecSDK UNKNOWN IMPORTED)
        set_target_properties(ob::OrbbecSDK PROPERTIES
            IMPORTED_LOCATION "${OrbbecSDK_LIBRARY}"
            INTERFACE_INCLUDE_DIRECTORIES "${OrbbecSDK_INCLUDE_DIR}")
    endif()
endif()
