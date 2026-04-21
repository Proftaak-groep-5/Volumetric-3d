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
    FetchContent_Declare(
        nlohmann_json
        GIT_REPOSITORY https://github.com/nlohmann/json.git
        GIT_TAG v3.11.3
    )
    FetchContent_Declare(
        spdlog
        GIT_REPOSITORY https://github.com/gabime/spdlog.git
        GIT_TAG v1.14.1
    )
    FetchContent_Declare(
        crow
        GIT_REPOSITORY https://github.com/CrowCpp/Crow.git
        GIT_TAG v1.2.1
    )
    set(ZSTD_BUILD_SHARED OFF CACHE BOOL "" FORCE)
    set(ZSTD_BUILD_PROGRAMS OFF CACHE BOOL "" FORCE)
    set(ZSTD_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(ZSTD_LEGACY_SUPPORT OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
        zstd
        GIT_REPOSITORY https://github.com/facebook/zstd.git
        GIT_TAG v1.5.6
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
    ${CMAKE_CURRENT_BINARY_DIR}/generated/BuildFeatures.hpp
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

install(TARGETS FemtoBoltNuc RUNTIME DESTINATION .)
install(FILES config/example.json DESTINATION config RENAME example.json)
install(FILES README.md TASKS.md DESTINATION .)
