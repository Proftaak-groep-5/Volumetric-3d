#include "app/App.hpp"

#include "http/HttpServer.hpp"
#include "orbbec/OrbbecCamera.hpp"
#include "orbbec/SyntheticFrameGenerator.hpp"
#include "streaming/DepthBinaryPublisher.hpp"
#include "streaming/PreviewPublisher.hpp"
#include "util/BuildFeatures.hpp"
#include "util/ImageIO.hpp"
#include "util/Log.hpp"
#include "util/NetUtils.hpp"
#include "discovery/SsdpService.hpp"

#include <winsock2.h>
#include <windows.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstdio>
#include <ctime>
#include <filesystem>
#include <iomanip>
#include <optional>
#include <sstream>
#include <string_view>
#include <thread>

namespace femto {
namespace {

App *g_app = nullptr;

BOOL WINAPI consoleHandler(DWORD signal) {
    if((signal == CTRL_C_EVENT || signal == CTRL_BREAK_EVENT || signal == CTRL_CLOSE_EVENT || signal == CTRL_SHUTDOWN_EVENT) && g_app) {
        g_app->requestStop();
        return TRUE;
    }
    return FALSE;
}

std::string isoNowUtc() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm tm {};
    gmtime_s(&tm, &time);
    std::ostringstream stream;
    stream << std::put_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
    return stream.str();
}

std::vector<uint8_t> depthToPreviewRgb(const std::vector<uint16_t> &values, int width, int height, int minDepthMm, int maxDepthMm, float scale,
                                       const std::string &mode) {
    std::vector<uint8_t> rgb(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 3);
    const auto range = std::max(1, maxDepthMm - minDepthMm);
    for(int i = 0; i < width * height; ++i) {
        const int depthMm = static_cast<int>(static_cast<float>(values[static_cast<std::size_t>(i)]) * scale);
        if(depthMm <= 0) {
            rgb[3 * i + 0] = 0;
            rgb[3 * i + 1] = 0;
            rgb[3 * i + 2] = 0;
            continue;
        }
        const float t = std::clamp(static_cast<float>(depthMm - minDepthMm) / static_cast<float>(range), 0.0f, 1.0f);
        if(mode == "grayscale") {
            const auto value = static_cast<uint8_t>(255.0f * (1.0f - t));
            rgb[3 * i + 0] = value;
            rgb[3 * i + 1] = value;
            rgb[3 * i + 2] = value;
        }
        else {
            const auto r = static_cast<uint8_t>(255.0f * std::clamp(1.5f - std::abs(4.0f * t - 3.0f), 0.0f, 1.0f));
            const auto g = static_cast<uint8_t>(255.0f * std::clamp(1.5f - std::abs(4.0f * t - 2.0f), 0.0f, 1.0f));
            const auto b = static_cast<uint8_t>(255.0f * std::clamp(1.5f - std::abs(4.0f * t - 1.0f), 0.0f, 1.0f));
            rgb[3 * i + 0] = r;
            rgb[3 * i + 1] = g;
            rgb[3 * i + 2] = b;
        }
    }
    return rgb;
}

std::vector<uint8_t> resizeRgbNearest(const std::vector<uint8_t> &src, int srcWidth, int srcHeight, int dstWidth, int dstHeight) {
    if(srcWidth == dstWidth && srcHeight == dstHeight) {
        return src;
    }
    std::vector<uint8_t> dst(static_cast<std::size_t>(dstWidth) * static_cast<std::size_t>(dstHeight) * 3);
    for(int y = 0; y < dstHeight; ++y) {
        const int srcY = y * srcHeight / dstHeight;
        for(int x = 0; x < dstWidth; ++x) {
            const int srcX = x * srcWidth / dstWidth;
            const auto srcIndex = static_cast<std::size_t>((srcY * srcWidth + srcX) * 3);
            const auto dstIndex = static_cast<std::size_t>((y * dstWidth + x) * 3);
            dst[dstIndex + 0] = src[srcIndex + 0];
            dst[dstIndex + 1] = src[srcIndex + 1];
            dst[dstIndex + 2] = src[srcIndex + 2];
        }
    }
    return dst;
}

std::optional<std::filesystem::path> findFlagPath(int argc, char **argv, const std::string &flag) {
    for(int i = 1; i < argc; ++i) {
        if(std::string(argv[i]) == flag) {
            if(i + 1 < argc && argv[i + 1][0] != '-') {
                return std::filesystem::path(argv[i + 1]);
            }
            return std::filesystem::path("test-output");
        }
    }
    return std::nullopt;
}

std::filesystem::path executableDirectory() {
    std::vector<char> buffer(MAX_PATH);
    DWORD length = 0;
    while(true) {
        length = GetModuleFileNameA(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
        if(length == 0) {
            return {};
        }
        if(length < buffer.size() - 1) {
            return std::filesystem::path(std::string(buffer.data(), length)).parent_path();
        }
        buffer.resize(buffer.size() * 2);
    }
}

bool isConfiguredPath(std::string_view value) {
    return !value.empty() && value != "not-found" && value.find("-NOTFOUND") == std::string_view::npos;
}

void prependToPathEnvironment(const std::filesystem::path &entry) {
    const auto entryString = entry.string();
    if(entryString.empty()) {
        return;
    }

    char *currentRaw = nullptr;
    size_t currentLength = 0;
    _dupenv_s(&currentRaw, &currentLength, "PATH");
    std::string currentPath = currentRaw ? currentRaw : "";
    if(currentRaw) {
        free(currentRaw);
    }

    if(currentPath.find(entryString) != std::string::npos) {
        return;
    }

    const std::string updatedPath = currentPath.empty() ? entryString : (entryString + ";" + currentPath);
    _putenv_s("PATH", updatedPath.c_str());
}

}  // namespace

App::App() = default;

App::~App() {
    requestStop();
}

int App::run(int argc, char **argv) {
    config_ = Config::loadFromArgs(argc, argv);
    log::init(config_.logLevel);

    if(const auto testOutputDir = findFlagPath(argc, argv, "--test-capture")) {
        return runTestCapture(*testOutputDir);
    }

    WSADATA wsaData {};
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    camera_ = std::make_unique<OrbbecCamera>(config_, stats_);
    synthetic_ = std::make_unique<SyntheticFrameGenerator>(config_);
    colorPreview_ = std::make_unique<PreviewPublisher>("color-preview");
    depthPreview_ = std::make_unique<PreviewPublisher>("depth-preview");
    depthBinary_ = std::make_unique<DepthBinaryPublisher>(config_, stats_);
    http_ = std::make_unique<HttpServer>(config_);
    discovery_ = std::make_unique<SsdpService>(config_);

    wireCallbacks();

    g_app = this;
    SetConsoleCtrlHandler(consoleHandler, TRUE);
    logRuntimeDependencyHints();
    configureRuntimeEnvironment();

    colorPreview_->start(config_.color.width, config_.color.height, config_.color.fps);
    depthPreview_->start(config_.depth.width, config_.depth.height, config_.depth.fps);
    http_->start({
        [this] { return healthJson(); },
        [this] { return heartbeatJson(); },
        [this] { return metadataJson(); },
        [this] { return streamsJson(); },
        [this] { return camera_->settingsJson(); },
        [this](const nlohmann::json &patch) { return camera_->applySettings(patch); },
        [this] {
            camera_->requestRestartStreams();
            return nlohmann::json{ { "ok", true }, { "requested", "restart_streams" } };
        },
        [this] { return camera_->capabilitiesJson(); },
        [this] { return statsJson(); },
        [this] {
            camera_->requestReconnect();
            return nlohmann::json{ { "ok", true }, { "requested", "reconnect" } };
        },
        [this] {
            camera_->requestRestartStreams();
            return nlohmann::json{ { "ok", true }, { "requested", "restart" } };
        },
        [this] { return colorPreview_->latestJpeg(); },
        [this] { return depthPreview_->latestJpeg(); },
        [this]() -> std::optional<HttpServer::DepthSnapshot> {
            const auto depth = latestDepthFrameForSnapshots();
            if(!depth) {
                return std::nullopt;
            }
            auto png = imageio::encodeGray16Png(depth->values.data(), depth->width, depth->height);
            if(!png) {
                return std::nullopt;
            }
            return HttpServer::DepthSnapshot { png, depth->depthScale, depth->width, depth->height, depth->format };
        },
        [this] { return depthBinary_->latestPacket(); },
        [this] { return discoveryJson(); },
    });

    discovery_->start([this] { return discoveryJson(); });
    camera_->start();
    synthetic_->start([this] { return syntheticSourceEnabled(); });

    const auto ip = net::firstReachableIpv4();
    log::get()->info("event=service urls root=http://{}:{}/ health=http://{}:{}/health depth_ws=ws://{}:{}/ws/depth", ip, config_.httpPort, ip,
                     config_.httpPort, ip, config_.httpPort);

    while(!stopRequested_) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    discovery_->stop();
    http_->stop();
    synthetic_->stop();
    camera_->stop();
    colorPreview_->stop();
    depthPreview_->stop();
    WSACleanup();
    g_app = nullptr;
    return 0;
}

int App::runTestCapture(const std::filesystem::path &outputDir) {
    camera_ = std::make_unique<OrbbecCamera>(config_, stats_);
    synthetic_ = std::make_unique<SyntheticFrameGenerator>(config_);
    camera_->start();
    synthetic_->start([this] { return syntheticSourceEnabled(); });

    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while(std::chrono::steady_clock::now() < deadline) {
        const auto color = camera_->latestColorFrame().has_value() || (synthetic_ && synthetic_->latestColorFrame().has_value());
        const auto depth = camera_->latestDepthFrame().has_value() || (synthetic_ && synthetic_->latestDepthFrame().has_value());
        if((camera_->connected() || syntheticSourceEnabled()) && color && depth) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    const auto metadata = metadataJson();
    auto color = camera_->latestColorFrame();
    if(!color && synthetic_) {
        color = synthetic_->latestColorFrame();
    }
    auto depth = camera_->latestDepthFrame();
    if(!depth && synthetic_) {
        depth = synthetic_->latestDepthFrame();
    }
    if((!camera_->connected() && !syntheticSourceEnabled()) || !color || !depth) {
        log::get()->error("test capture failed: connected={} synthetic_active={} color={} depth={} error={}", camera_->connected(),
                          synthetic_ ? synthetic_->active() : false, static_cast<bool>(color), static_cast<bool>(depth), camera_->lastError());
        synthetic_->stop();
        camera_->stop();
        return 2;
    }

    std::filesystem::create_directories(outputDir);
    const auto metadataPath = outputDir / "metadata.json";
    const auto colorPath = outputDir / "color.jpg";
    const auto depthPath = outputDir / "depth.png";

    {
        FILE *file = nullptr;
        if(_wfopen_s(&file, metadataPath.wstring().c_str(), L"wb") == 0 && file) {
            const auto text = metadata.dump(2);
            fwrite(text.data(), 1, text.size(), file);
            fclose(file);
        }
    }

    const auto wroteColor = imageio::writeRgbJpegFile(colorPath, color->bytes.data(), color->width, color->height);
    const auto wroteDepth = imageio::writeGray16PngFile(depthPath, depth->values.data(), depth->width, depth->height);

    log::get()->info("test capture metadata: {}", metadata.dump(2));
    log::get()->info("test capture saved color={} depth={} output={}", wroteColor, wroteDepth, outputDir.string());
    synthetic_->stop();
    camera_->stop();
    return (wroteColor && wroteDepth) ? 0 : 3;
}

void App::requestStop() {
    stopRequested_ = true;
}

void App::wireCallbacks() {
    camera_->setColorCallback([this](const OrbbecCamera::FrameEnvelope &frame) { handleColorFrame(frame); });
    camera_->setDepthCallback(
        [this](const OrbbecCamera::DepthEnvelope &frame) { handleDepthFrame(frame, camera_->metadataJson().value("calibration", nlohmann::json(nullptr))); });
    synthetic_->setColorCallback([this](const OrbbecCamera::FrameEnvelope &frame) {
        stats_.onColorInputFrame();
        handleColorFrame(frame);
    });
    synthetic_->setDepthCallback([this](const OrbbecCamera::DepthEnvelope &frame) {
        stats_.onDepthInputFrame();
        handleDepthFrame(frame, nullptr);
    });

    colorPreview_->setFrameCallback([this](std::shared_ptr<const std::vector<uint8_t>> jpeg, uint64_t, double encodeMs) {
        stats_.onColorPreviewFrame(jpeg ? jpeg->size() : 0, encodeMs);
        http_->publishColorPreview(std::move(jpeg));
    });
    depthPreview_->setFrameCallback([this](std::shared_ptr<const std::vector<uint8_t>> jpeg, uint64_t, double encodeMs) {
        stats_.onDepthPreviewFrame(jpeg ? jpeg->size() : 0, encodeMs);
        http_->publishDepthPreview(std::move(jpeg));
    });
    depthBinary_->setPacketCallback([this](std::shared_ptr<const std::vector<uint8_t>> packet) {
        http_->publishDepthBinary(std::move(packet));
    });
}

void App::handleColorFrame(const OrbbecCamera::FrameEnvelope &frame) {
    if(camera_->runtimeSettings().colorEnabled) {
        auto resized = resizeRgbNearest(frame.bytes, frame.width, frame.height, config_.color.width, config_.color.height);
        if(!colorPreview_->pushRgbFrame(resized.data(), resized.size(), frame.timestampUs)) {
            stats_.onDroppedOutputFrame();
        }
    }
}

void App::handleDepthFrame(const OrbbecCamera::DepthEnvelope &frame, const nlohmann::json &calibration) {
    publishDepthPreview(frame.values, frame.width, frame.height, frame.depthScale, frame.timestampUs);
    depthBinary_->publishFrame(frame.values, frame.width, frame.height, frame.frameIndex, frame.timestampUs, frame.systemTimestampUs, frame.depthScale,
                               calibration, frame.format);
}

void App::logRuntimeDependencyHints() const {
    log::get()->info("event=runtime_dependency name=orbbec_sdk available={} root={}", ORBBECSDK_FOUND, FEMTOBOLTNUC_ORBBEC_ROOT);
    log::get()->info("event=runtime_dependency name=gstreamer available={} root={} plugin_dir={}", GStreamerWindows_FOUND, FEMTOBOLTNUC_GSTREAMER_ROOT,
                     FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR);
    log::get()->info("event=runtime_dlls orbbec=OrbbecSDK.dll gstreamer=gstreamer-1.0-0.dll,gstapp-1.0-0.dll,gstbase-1.0-0.dll,gstvideo-1.0-0.dll");
    log::get()->info("event=service_config synthetic_enabled={} synthetic_use_when_no_camera={} synthetic_force_no_camera={}", config_.syntheticInput.enabled,
                     config_.syntheticInput.useWhenNoCamera, config_.syntheticInput.forceNoCamera);
    if(!GStreamerWindows_FOUND) {
        log::get()->warn("event=runtime_dependency_missing name=gstreamer action=preview_streams_disabled detail=\"Build without GStreamer or finder failed\"");
    }
    if(!ORBBECSDK_FOUND) {
        log::get()->warn("event=runtime_dependency_missing name=orbbec_sdk action=no_camera_mode_only detail=\"Build without Orbbec SDK or finder failed\"");
    }
}

void App::configureRuntimeEnvironment() const {
#if GStreamerWindows_FOUND
    const auto exeDir = executableDirectory();
    const auto bundledPluginDir = exeDir / "gstreamer-plugins";
    const auto bundledScanner = exeDir / "gstreamer-libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe";
    const std::string gstRoot = FEMTOBOLTNUC_GSTREAMER_ROOT;
    const std::string gstPluginDir = FEMTOBOLTNUC_GSTREAMER_PLUGIN_DIR;

    prependToPathEnvironment(exeDir);
    log::get()->info("event=runtime_env variable=PATH prepend={} reason=executable_dir", exeDir.string());

    if(std::filesystem::exists(bundledPluginDir)) {
        _putenv_s("GST_PLUGIN_PATH", bundledPluginDir.string().c_str());
        _putenv_s("GST_PLUGIN_SYSTEM_PATH_1_0", bundledPluginDir.string().c_str());
        log::get()->info("event=runtime_env variable=GST_PLUGIN_PATH value={} reason=bundled_plugins", bundledPluginDir.string());
    }
    else if(isConfiguredPath(gstPluginDir) && std::filesystem::exists(gstPluginDir)) {
        _putenv_s("GST_PLUGIN_PATH", gstPluginDir.c_str());
        _putenv_s("GST_PLUGIN_SYSTEM_PATH_1_0", gstPluginDir.c_str());
        log::get()->info("event=runtime_env variable=GST_PLUGIN_PATH value={} reason=system_install", gstPluginDir);
    }
    else {
        log::get()->warn("event=runtime_env_missing variable=GST_PLUGIN_PATH detail=plugin_dir_unresolved");
    }

    if(std::filesystem::exists(bundledScanner)) {
        _putenv_s("GST_PLUGIN_SCANNER", bundledScanner.string().c_str());
        log::get()->info("event=runtime_env variable=GST_PLUGIN_SCANNER value={} reason=bundled_scanner", bundledScanner.string());
    }

    if(isConfiguredPath(gstRoot)) {
        const auto gstBinDir = std::filesystem::path(gstRoot) / "bin";
        if(std::filesystem::exists(gstBinDir)) {
            prependToPathEnvironment(gstBinDir);
            log::get()->info("event=runtime_env variable=PATH prepend={} reason=gstreamer_runtime_dlls", gstBinDir.string());
        }
    }
#endif
}

bool App::syntheticSourceEnabled() const {
    if(!synthetic_ || !config_.syntheticInput.enabled) {
        return false;
    }
    if(config_.syntheticInput.forceNoCamera) {
        return true;
    }
    return config_.syntheticInput.useWhenNoCamera && !camera_->connected();
}

std::optional<OrbbecCamera::DepthEnvelope> App::latestDepthFrameForSnapshots() const {
    if(auto depth = camera_->latestDepthFrame()) {
        return depth;
    }
    if(synthetic_) {
        return synthetic_->latestDepthFrame();
    }
    return std::nullopt;
}

nlohmann::json App::metadataJson() const {
    auto metadata = camera_->metadataJson();
    metadata["active_configuration"] = Config::toJson(config_);
    metadata["endpoints"] = streamsJson();
    metadata["source"] = {
        { "mode", sourceMode() },
        { "camera_connected", camera_->connected() },
        { "synthetic_enabled", config_.syntheticInput.enabled },
        { "synthetic_active", synthetic_ ? synthetic_->active() : false },
    };

    if(sourceMode() == "synthetic" && metadata.value("device", nlohmann::json(nullptr)).is_null()) {
        const auto syntheticColorProfiles = nlohmann::json::array(
            { nlohmann::json{ { "width", config_.color.width }, { "height", config_.color.height }, { "fps", config_.color.fps }, { "format", "RGB" } } });
        const auto syntheticDepthProfiles = nlohmann::json::array(
            { nlohmann::json{ { "width", config_.depth.width }, { "height", config_.depth.height }, { "fps", config_.depth.fps }, { "format", "Z16" } } });
        metadata["device"] = {
            { "serial_number", "synthetic" },
            { "name", "Synthetic Femto Bolt" },
            { "firmware_version", nullptr },
            { "connection_type", "synthetic" },
            { "uid", config_.instanceId + "-synthetic" },
        };
        metadata["stream_capabilities"] = {
            { "supported_color_profiles", syntheticColorProfiles },
            { "supported_depth_profiles", syntheticDepthProfiles },
        };
        metadata["current_profiles"] = {
            { "color", { { "width", config_.color.width }, { "height", config_.color.height }, { "fps", config_.color.fps }, { "format", "RGB" } } },
            { "depth", { { "width", config_.depth.width }, { "height", config_.depth.height }, { "fps", config_.depth.fps }, { "format", "Z16" } } },
        };
        metadata["depth_scale"] = config_.syntheticInput.depthScale;
        metadata["calibration"] = nullptr;
    }

    return metadata;
}

nlohmann::json App::statsJson() const {
    auto stats = stats_.snapshot();
    stats["source_mode"] = sourceMode();
    stats["camera_connected"] = camera_->connected();
    stats["synthetic_active"] = synthetic_ ? synthetic_->active() : false;
    return stats;
}

std::string App::sourceMode() const {
    if(camera_->connected()) {
        return "camera";
    }
    if(synthetic_ && synthetic_->active()) {
        return "synthetic";
    }
    return "no_camera";
}

void App::publishDepthPreview(const std::vector<uint16_t> &values, int width, int height, float depthScale, uint64_t timestampUs) {
    const auto settings = camera_->runtimeSettings();
    if(!settings.depthPreviewEnabled) {
        return;
    }
    auto rgb = depthToPreviewRgb(values, width, height, settings.depthPreviewMinMm, settings.depthPreviewMaxMm, depthScale, config_.depthPreview.mode);
    auto resized = resizeRgbNearest(rgb, width, height, config_.depth.width, config_.depth.height);
    if(!depthPreview_->pushRgbFrame(resized.data(), resized.size(), timestampUs)) {
        stats_.onDroppedOutputFrame();
    }
}

nlohmann::json App::healthJson() const {
    const bool connected = camera_->connected();
    const auto runtime = camera_->runtimeSettings();
    const auto stats = stats_.snapshot();
    const bool previewsHealthy = (!runtime.colorEnabled || colorPreview_->running()) && (!runtime.depthPreviewEnabled || depthPreview_->running());
    const auto mode = sourceMode();
    return {
        { "status", connected && previewsHealthy ? "ready" : "degraded" },
        { "uptime_sec", stats_.uptimeSeconds() },
        { "app_version", FEMTOBOLTNUC_VERSION },
        { "camera_connected", connected },
        { "source_mode", mode },
        { "current_stream_states",
          {
              { "color_preview", runtime.colorEnabled },
              { "depth_preview", runtime.depthPreviewEnabled },
              { "authoritative_depth", runtime.depthBinaryEnabled },
          } },
        { "dropped_frame_counters",
          {
              { "input", stats.value("dropped_input_frames", 0) },
              { "output", stats.value("dropped_output_frames", 0) },
          } },
        { "last_error_summary", camera_->lastError() },
    };
}

nlohmann::json App::heartbeatJson() const {
    return {
        { "timestamp_utc", isoNowUtc() },
        { "instance_id", config_.instanceId },
        { "camera_serial", camera_->cameraSerial() },
        { "state", sourceMode() },
    };
}

nlohmann::json App::streamsJson() const {
    const auto host = net::firstReachableIpv4();
    const auto baseHttp = "http://" + host + ":" + std::to_string(config_.httpPort);
    const auto baseWs = "ws://" + host + ":" + std::to_string(config_.httpPort);
    return {
        { "color_preview_url", baseWs + "/ws/preview/color" },
        { "depth_preview_url", baseWs + "/ws/preview/depth" },
        { "depth_binary_ws_url", baseWs + "/ws/depth" },
        { "depth_snapshot_url", baseHttp + "/snapshot/depth.png" },
        { "depth_binary_snapshot_url", baseHttp + "/snapshot/depth.bin" },
        { "color_snapshot_url", baseHttp + "/snapshot/color.jpg" },
        { "signaling_url", nullptr },
        { "local_discovery_info_url", baseHttp + "/discovery" },
        { "codec",
          {
              { "color_preview", "image/jpeg over websocket" },
              { "depth_preview", "image/jpeg over websocket" },
              { "depth_binary", config_.depthBinary.compression + " over websocket" },
          } },
        { "publisher_interface", "IPreviewPublisher" },
        { "webrtc_status", "not_implemented" },
    };
}

nlohmann::json App::discoveryJson() const {
    const auto host = net::firstReachableIpv4();
    return {
        { "service_name", "FemtoBoltNuc" },
        { "instance_id", config_.instanceId },
        { "hostname_or_ip", host },
        { "http_port", config_.httpPort },
        { "serial_number", camera_->cameraSerial().empty() && sourceMode() == "synthetic" ? "synthetic" : camera_->cameraSerial() },
        { "model", camera_->cameraName().empty() && sourceMode() == "synthetic" ? "Synthetic Femto Bolt" : camera_->cameraName() },
        { "endpoint_paths",
          {
              { "root", "/" },
              { "health", "/health" },
              { "metadata", "/metadata" },
              { "depth_ws", "/ws/depth" },
              { "color_preview_ws", "/ws/preview/color" },
              { "depth_preview_ws", "/ws/preview/depth" },
          } },
        { "version", FEMTOBOLTNUC_VERSION },
        { "health_state", camera_->connected() ? "ready" : "degraded" },
        { "source_mode", sourceMode() },
    };
}

}  // namespace femto
