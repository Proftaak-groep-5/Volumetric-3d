cmake_minimum_required(VERSION 3.24)

project(FemtoBoltNuc
    VERSION 0.1.0
    DESCRIPTION "Intel NUC service for Orbbec Femto Bolt streaming and control"
    LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(NUC_FETCH_DEPS "Fetch third-party dependencies with FetchContent" ON)
option(NUC_REQUIRE_ORBBEC "Fail configure if Orbbec SDK is not found" OFF)
option(NUC_REQUIRE_GSTREAMER "Fail configure if GStreamer is not found" OFF)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

set(FEMTOBOLTNUC_ORBBEC_ROOT "not-found")
set(FEMTOBOLTNUC_GSTREAMER_ROOT "not-found")
set(FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR "not-found")

include(FetchContent)

if(POLICY CMP0168)
    cmake_policy(SET CMP0168 NEW)
endif()

set(FETCHCONTENT_UPDATES_DISCONNECTED ON)

if(MSVC)
    add_compile_options(/W4 /permissive- /EHsc)
    add_compile_definitions(
        WIN32_LEAN_AND_MEAN
        NOMINMAX
        _CRT_SECURE_NO_WARNINGS
        _SILENCE_CXX17_CODECVT_HEADER_DEPRECATION_WARNING)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

if(NUC_FETCH_DEPS)
    if(NOT ASIO_INCLUDE_DIR OR NOT EXISTS "${ASIO_INCLUDE_DIR}/asio.hpp")
        FetchContent_Declare(
            asio
            URL https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-30-2.tar.gz
            URL_HASH SHA256=755bd7f85a4b269c67ae0ea254907c078d408cce8e1a352ad2ed664d233780e8
        )
        FetchContent_MakeAvailable(asio)
        set(ASIO_INCLUDE_DIR "${asio_SOURCE_DIR}/asio/include")
    endif()
    set(ASIO_INCLUDE_DIR "${ASIO_INCLUDE_DIR}" CACHE PATH "Path to standalone Asio include directory" FORCE)

    FetchContent_Declare(
        nlohmann_json
        URL https://github.com/nlohmann/json/archive/refs/tags/v3.11.3.tar.gz
        URL_HASH SHA256=0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406
    )
    FetchContent_Declare(
        spdlog
        URL https://github.com/gabime/spdlog/archive/refs/tags/v1.14.1.tar.gz
        URL_HASH SHA256=1586508029a7d0670dfcb2d97575dcdc242d3868a259742b69f100801ab4e16b
    )
    FetchContent_Declare(
        crow
        URL https://github.com/CrowCpp/Crow/archive/refs/tags/v1.2.1.tar.gz
        URL_HASH SHA256=552f2e447adf70ed4c667d6f82db53dfc70710b50431004ab1405f5b53f04c30
    )
    set(ZSTD_BUILD_SHARED OFF CACHE BOOL "" FORCE)
    set(ZSTD_BUILD_PROGRAMS OFF CACHE BOOL "" FORCE)
    set(ZSTD_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(ZSTD_LEGACY_SUPPORT OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
        zstd
        URL https://github.com/facebook/zstd/archive/refs/tags/v1.5.6.tar.gz
        URL_HASH SHA256=30f35f71c1203369dc979ecde0400ffea93c27391bfd2ac5a9715d2173d92ff7
        SOURCE_SUBDIR build/cmake
    )
    FetchContent_MakeAvailable(nlohmann_json spdlog crow zstd)
endif()

find_package(Threads REQUIRED)

set(ORBBECSDK_FOUND FALSE)
find_package(OrbbecSDK CONFIG QUIET)
if(TARGET ob::OrbbecSDK)
    set(ORBBECSDK_FOUND TRUE)
    set(ORBBECSDK_TARGET ob::OrbbecSDK)
elseif(TARGET OrbbecSDK::OrbbecSDK)
    set(ORBBECSDK_FOUND TRUE)
    set(ORBBECSDK_TARGET OrbbecSDK::OrbbecSDK)
else()
    find_package(OrbbecSDK QUIET)
    if(TARGET ob::OrbbecSDK)
        set(ORBBECSDK_FOUND TRUE)
        set(ORBBECSDK_TARGET ob::OrbbecSDK)
    elseif(TARGET OrbbecSDK::OrbbecSDK)
        set(ORBBECSDK_FOUND TRUE)
        set(ORBBECSDK_TARGET OrbbecSDK::OrbbecSDK)
    endif()
endif()
if(NUC_REQUIRE_ORBBEC AND NOT ORBBECSDK_FOUND)
    message(FATAL_ERROR
        "Orbbec SDK v2 not found.\n"
        "Set OrbbecSDK_DIR to the SDK lib directory, for example:\n"
        "  C:/Program Files/OrbbecSDK 2.7.6/lib\n"
        "or set ORBBECSDK_ROOT / ORBBEC_SDK_ROOT to the SDK root.\n"
        "Checked hints:\n"
        "  - ${OrbbecSDK_SEARCH_HINTS}")
endif()
if(ORBBECSDK_FOUND)
    if(DEFINED OrbbecSDK_INCLUDE_DIR)
        get_filename_component(FEMTOBOLTNUC_ORBBEC_ROOT "${OrbbecSDK_INCLUDE_DIR}" DIRECTORY)
    elseif(DEFINED OrbbecSDK_DIR)
        set(FEMTOBOLTNUC_ORBBEC_ROOT "${OrbbecSDK_DIR}")
    endif()
    if(FEMTOBOLTNUC_ORBBEC_ROOT AND NOT FEMTOBOLTNUC_ORBBEC_ROOT STREQUAL "not-found")
        file(TO_CMAKE_PATH "${FEMTOBOLTNUC_ORBBEC_ROOT}" FEMTOBOLTNUC_ORBBEC_ROOT)
        get_filename_component(_orbbec_root_name "${FEMTOBOLTNUC_ORBBEC_ROOT}" NAME)
        if(_orbbec_root_name STREQUAL "lib")
            get_filename_component(FEMTOBOLTNUC_ORBBEC_ROOT "${FEMTOBOLTNUC_ORBBEC_ROOT}" DIRECTORY)
        endif()
    endif()
    if(FEMTOBOLTNUC_ORBBEC_ROOT AND EXISTS "${FEMTOBOLTNUC_ORBBEC_ROOT}/bin")
        set(FEMTOBOLTNUC_ORBBEC_BIN_DIR "${FEMTOBOLTNUC_ORBBEC_ROOT}/bin")
    elseif(DEFINED OrbbecSDK_DLL AND EXISTS "${OrbbecSDK_DLL}")
        get_filename_component(FEMTOBOLTNUC_ORBBEC_BIN_DIR "${OrbbecSDK_DLL}" DIRECTORY)
    endif()
    if(FEMTOBOLTNUC_ORBBEC_BIN_DIR AND EXISTS "${FEMTOBOLTNUC_ORBBEC_BIN_DIR}/OrbbecSDKConfig.xml")
        set(FEMTOBOLTNUC_ORBBEC_CONFIG_XML "${FEMTOBOLTNUC_ORBBEC_BIN_DIR}/OrbbecSDKConfig.xml")
    endif()
    if(FEMTOBOLTNUC_ORBBEC_BIN_DIR AND EXISTS "${FEMTOBOLTNUC_ORBBEC_BIN_DIR}/extensions")
        set(FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR "${FEMTOBOLTNUC_ORBBEC_BIN_DIR}/extensions")
    endif()
endif()

find_package(GStreamerWindows QUIET)
if(NUC_REQUIRE_GSTREAMER AND NOT GStreamerWindows_FOUND)
    message(FATAL_ERROR
        "GStreamer 1.0 MSVC x64 not found.\n"
        "Set GSTREAMER_ROOT_DIR or GSTREAMER_1_0_ROOT_MSVC_X86_64 to the install root, for example:\n"
        "  C:/gstreamer/1.0/msvc_x86_64\n"
        "Checked hints:\n"
        "  - ${GStreamerWindows_SEARCH_HINTS}")
endif()
if(GStreamerWindows_FOUND)
    if(DEFINED GStreamerWindows_INCLUDE_DIR)
        get_filename_component(_gstreamer_include_root "${GStreamerWindows_INCLUDE_DIR}" DIRECTORY)
        get_filename_component(FEMTOBOLTNUC_GSTREAMER_ROOT "${_gstreamer_include_root}" DIRECTORY)
    endif()
    if(DEFINED GStreamerWindows_PLUGIN_DIR)
        set(FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR "${GStreamerWindows_PLUGIN_DIR}")
    elseif(FEMTOBOLTNUC_GSTREAMER_ROOT AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_ROOT}/lib/gstreamer-1.0")
        set(FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR "${FEMTOBOLTNUC_GSTREAMER_ROOT}/lib/gstreamer-1.0")
    endif()
    if(FEMTOBOLTNUC_GSTREAMER_ROOT AND NOT FEMTOBOLTNUC_GSTREAMER_ROOT STREQUAL "not-found")
        file(TO_CMAKE_PATH "${FEMTOBOLTNUC_GSTREAMER_ROOT}" FEMTOBOLTNUC_GSTREAMER_ROOT)
    endif()
    if(FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR AND NOT FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR STREQUAL "not-found")
        file(TO_CMAKE_PATH "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR}" FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR)
    endif()
    if(FEMTOBOLTNUC_GSTREAMER_ROOT AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_ROOT}/bin")
        file(GLOB GStreamerWindows_BIN_DLLS "${FEMTOBOLTNUC_GSTREAMER_ROOT}/bin/*.dll")
    endif()
    if(FEMTOBOLTNUC_GSTREAMER_ROOT AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_ROOT}/libexec/gstreamer-1.0/gst-plugin-scanner.exe")
        set(FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER "${FEMTOBOLTNUC_GSTREAMER_ROOT}/libexec/gstreamer-1.0/gst-plugin-scanner.exe")
    endif()
endif()

find_package(ZSTD CONFIG QUIET)
if(TARGET zstd::libzstd_static)
    set(ZSTD_TARGET zstd::libzstd_static)
elseif(TARGET zstd::libzstd_shared)
    set(ZSTD_TARGET zstd::libzstd_shared)
elseif(TARGET libzstd_static)
    set(ZSTD_TARGET libzstd_static)
elseif(TARGET libzstd_shared)
    set(ZSTD_TARGET libzstd_shared)
elseif(TARGET zstd)
    set(ZSTD_TARGET zstd)
endif()
if(NOT ZSTD_TARGET)
    message(FATAL_ERROR "zstd target not found")
endif()

configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/src/util/BuildFeatures.hpp.in
    ${CMAKE_CURRENT_BINARY_DIR}/generated/util/BuildFeatures.hpp
    @ONLY)

set(APP_SOURCES
    src/main.cpp
    src/app/App.cpp
    src/config/Config.cpp
    src/discovery/SsdpService.cpp
    src/http/HttpServer.cpp
    src/orbbec/OrbbecCamera.cpp
    src/orbbec/SyntheticFrameGenerator.cpp
    src/streaming/DepthBinaryPublisher.cpp
    src/streaming/PreviewPublisher.cpp
    src/util/ImageIO.cpp
    src/util/Log.cpp
    src/util/NetUtils.cpp
    src/util/StatsCollector.cpp)

add_executable(FemtoBoltNuc ${APP_SOURCES})

target_include_directories(FemtoBoltNuc
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${CMAKE_CURRENT_BINARY_DIR}/generated)

if(ASIO_INCLUDE_DIR)
    target_include_directories(FemtoBoltNuc PRIVATE ${ASIO_INCLUDE_DIR})
endif()

target_link_libraries(FemtoBoltNuc
    PRIVATE
        Crow::Crow
        nlohmann_json::nlohmann_json
        spdlog::spdlog
        Threads::Threads
        ${ZSTD_TARGET}
        ws2_32
        iphlpapi
        windowscodecs
        ole32
        oleaut32)

if(ORBBECSDK_FOUND)
    target_compile_definitions(FemtoBoltNuc PRIVATE NUC_HAS_ORBBEC=1)
    target_link_libraries(FemtoBoltNuc PRIVATE ${ORBBECSDK_TARGET})
else()
    target_compile_definitions(FemtoBoltNuc PRIVATE NUC_HAS_ORBBEC=0)
endif()

if(GStreamerWindows_FOUND)
    target_compile_definitions(FemtoBoltNuc PRIVATE NUC_HAS_GSTREAMER=1)
    target_include_directories(FemtoBoltNuc PRIVATE ${GStreamerWindows_INCLUDE_DIRS})
    target_link_libraries(FemtoBoltNuc PRIVATE ${GStreamerWindows_LIBRARIES})
else()
    target_compile_definitions(FemtoBoltNuc PRIVATE NUC_HAS_GSTREAMER=0)
endif()

if(MSVC)
    target_compile_definitions(FemtoBoltNuc PRIVATE _WIN32_WINNT=0x0A00)
endif()

if(WIN32)
    add_custom_command(TARGET FemtoBoltNuc POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_RUNTIME_DLLS:FemtoBoltNuc>
            $<TARGET_FILE_DIR:FemtoBoltNuc>
        COMMAND_EXPAND_LISTS)

    if(ORBBECSDK_FOUND)
        get_target_property(_orbbecsdk_runtime_path ${ORBBECSDK_TARGET} IMPORTED_LOCATION)
        if(_orbbecsdk_runtime_path AND EXISTS "${_orbbecsdk_runtime_path}")
            add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "${_orbbecsdk_runtime_path}"
                    $<TARGET_FILE_DIR:FemtoBoltNuc>)
        elseif(DEFINED OrbbecSDK_DLL AND EXISTS "${OrbbecSDK_DLL}")
            add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "${OrbbecSDK_DLL}"
                    $<TARGET_FILE_DIR:FemtoBoltNuc>)
        elseif(DEFINED OrbbecSDK_DIR)
            get_filename_component(_orbbecsdk_hint_root "${OrbbecSDK_DIR}" DIRECTORY)
            set(_orbbecsdk_hint_dll "${_orbbecsdk_hint_root}/bin/OrbbecSDK.dll")
            if(EXISTS "${_orbbecsdk_hint_dll}")
                add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                    COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "${_orbbecsdk_hint_dll}"
                    $<TARGET_FILE_DIR:FemtoBoltNuc>)
            endif()
        endif()
        if(DEFINED FEMTOBOLTNUC_ORBBEC_CONFIG_XML AND EXISTS "${FEMTOBOLTNUC_ORBBEC_CONFIG_XML}")
            add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "${FEMTOBOLTNUC_ORBBEC_CONFIG_XML}"
                    $<TARGET_FILE_DIR:FemtoBoltNuc>)
        endif()
        if(DEFINED FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR AND EXISTS "${FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR}")
            add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E rm -rf
                    "$<TARGET_FILE_DIR:FemtoBoltNuc>/extensions"
                COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR}"
                    "$<TARGET_FILE_DIR:FemtoBoltNuc>/extensions")
        endif()
    endif()

    if(GStreamerWindows_FOUND)
        foreach(_gst_runtime_dll IN LISTS GStreamerWindows_RUNTIME_DLLS)
            if(_gst_runtime_dll AND EXISTS "${_gst_runtime_dll}")
                add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                    COMMAND ${CMAKE_COMMAND} -E copy_if_different
                        "${_gst_runtime_dll}"
                        $<TARGET_FILE_DIR:FemtoBoltNuc>)
            endif()
        endforeach()
        foreach(_gst_bin_dll IN LISTS GStreamerWindows_BIN_DLLS)
            if(_gst_bin_dll AND EXISTS "${_gst_bin_dll}")
                add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                    COMMAND ${CMAKE_COMMAND} -E copy_if_different
                        "${_gst_bin_dll}"
                        $<TARGET_FILE_DIR:FemtoBoltNuc>)
            endif()
        endforeach()
        if(FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR}")
            add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E rm -rf
                    "$<TARGET_FILE_DIR:FemtoBoltNuc>/gstreamer-plugins"
                COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR}"
                    "$<TARGET_FILE_DIR:FemtoBoltNuc>/gstreamer-plugins")
        endif()
        if(FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER}")
            add_custom_command(TARGET FemtoBoltNuc POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E make_directory
                    "$<TARGET_FILE_DIR:FemtoBoltNuc>/gstreamer-libexec/gstreamer-1.0"
                COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER}"
                    "$<TARGET_FILE_DIR:FemtoBoltNuc>/gstreamer-libexec/gstreamer-1.0")
        endif()
    endif()
endif()

install(TARGETS FemtoBoltNuc RUNTIME DESTINATION .)
if(WIN32)
    install(FILES $<TARGET_RUNTIME_DLLS:FemtoBoltNuc> DESTINATION .)
    if(ORBBECSDK_FOUND)
        if(DEFINED _orbbecsdk_runtime_path AND EXISTS "${_orbbecsdk_runtime_path}")
            install(FILES "${_orbbecsdk_runtime_path}" DESTINATION .)
        elseif(DEFINED OrbbecSDK_DLL AND EXISTS "${OrbbecSDK_DLL}")
            install(FILES "${OrbbecSDK_DLL}" DESTINATION .)
        elseif(DEFINED _orbbecsdk_hint_dll AND EXISTS "${_orbbecsdk_hint_dll}")
            install(FILES "${_orbbecsdk_hint_dll}" DESTINATION .)
        endif()
        if(DEFINED FEMTOBOLTNUC_ORBBEC_CONFIG_XML AND EXISTS "${FEMTOBOLTNUC_ORBBEC_CONFIG_XML}")
            install(FILES "${FEMTOBOLTNUC_ORBBEC_CONFIG_XML}" DESTINATION .)
        endif()
        if(DEFINED FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR AND EXISTS "${FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR}")
            install(DIRECTORY "${FEMTOBOLTNUC_ORBBEC_EXTENSIONS_DIR}/" DESTINATION extensions)
        endif()
    endif()
    if(GStreamerWindows_FOUND)
        foreach(_gst_runtime_dll IN LISTS GStreamerWindows_RUNTIME_DLLS)
            if(_gst_runtime_dll AND EXISTS "${_gst_runtime_dll}")
                install(FILES "${_gst_runtime_dll}" DESTINATION .)
            endif()
        endforeach()
        foreach(_gst_bin_dll IN LISTS GStreamerWindows_BIN_DLLS)
            if(_gst_bin_dll AND EXISTS "${_gst_bin_dll}")
                install(FILES "${_gst_bin_dll}" DESTINATION .)
            endif()
        endforeach()
        if(FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR}")
            install(DIRECTORY "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR}/" DESTINATION gstreamer-plugins)
        endif()
        if(FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER AND EXISTS "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER}")
            install(FILES "${FEMTOBOLTNUC_GSTREAMER_PLUGIN_SCANNER}" DESTINATION gstreamer-libexec/gstreamer-1.0)
        endif()
    endif()
endif()
install(FILES config/example.json DESTINATION config RENAME example.json)
install(FILES README.md TASKS.md DESTINATION .)
