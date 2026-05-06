#include "config/Config.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>

namespace femto {
namespace {

std::string getEnvOrDefault(const char *name, const std::string &fallback) {
    if(const char *value = std::getenv(name)) {
        return value;
    }
    return fallback;
}

template <typename T> void assignIfPresent(const nlohmann::json &node, const char *key, T &value) {
    if(node.contains(key) && !node.at(key).is_null()) {
        value = node.at(key).get<T>();
    }
}

Config loadJsonFile(const std::filesystem::path &path) {
    std::ifstream input(path);
    if(!input) {
        throw std::runtime_error("Failed to open config file: " + path.string());
    }
    nlohmann::json json;
    input >> json;
    return Config::fromJson(json);
}

}  // namespace

Config Config::fromJson(const nlohmann::json &json) {
    Config config;
    assignIfPresent(json, "instance_id", config.instanceId);
    assignIfPresent(json, "bind_address", config.bindAddress);
    assignIfPresent(json, "http_port", config.httpPort);
    assignIfPresent(json, "log_level", config.logLevel);

    if(json.contains("camera")) {
        const auto &camera = json.at("camera");
        assignIfPresent(camera, "serial_number", config.camera.serialNumber);
        assignIfPresent(camera, "auto_open_first_femto_bolt", config.camera.autoOpenFirstFemtoBolt);
        assignIfPresent(camera, "enable_global_timestamp", config.camera.enableGlobalTimestamp);
        assignIfPresent(camera, "retry_interval_ms", config.camera.retryIntervalMs);
    }

    if(json.contains("streams")) {
        const auto &streams = json.at("streams");
        if(streams.contains("color")) {
            const auto &color = streams.at("color");
            assignIfPresent(color, "enabled", config.color.enabled);
            assignIfPresent(color, "width", config.color.width);
            assignIfPresent(color, "height", config.color.height);
            assignIfPresent(color, "fps", config.color.fps);
            assignIfPresent(color, "target_bitrate_mbps", config.color.targetBitrateMbps);
            config.runtime.colorEnabled = config.color.enabled;
        }
        if(streams.contains("depth")) {
            const auto &depth = streams.at("depth");
            assignIfPresent(depth, "enabled", config.depth.enabled);
            assignIfPresent(depth, "width", config.depth.width);
            assignIfPresent(depth, "height", config.depth.height);
            assignIfPresent(depth, "fps", config.depth.fps);
            assignIfPresent(depth, "align_to_color", config.depth.alignToColor);
        }
        if(streams.contains("depth_preview")) {
            const auto &preview = streams.at("depth_preview");
            assignIfPresent(preview, "enabled", config.depthPreview.enabled);
            assignIfPresent(preview, "target_bitrate_mbps", config.depthPreview.targetBitrateMbps);
            assignIfPresent(preview, "mode", config.depthPreview.mode);
            assignIfPresent(preview, "min_depth_mm", config.depthPreview.minDepthMm);
            assignIfPresent(preview, "max_depth_mm", config.depthPreview.maxDepthMm);
            config.runtime.depthPreviewEnabled = config.depthPreview.enabled;
            config.runtime.depthPreviewMinMm = config.depthPreview.minDepthMm;
            config.runtime.depthPreviewMaxMm = config.depthPreview.maxDepthMm;
        }
        if(streams.contains("authoritative_depth")) {
            const auto &depthBinary = streams.at("authoritative_depth");
            assignIfPresent(depthBinary, "enabled", config.depthBinary.enabled);
            assignIfPresent(depthBinary, "compression", config.depthBinary.compression);
            assignIfPresent(depthBinary, "compression_level", config.depthBinary.compressionLevel);
            config.runtime.depthBinaryEnabled = config.depthBinary.enabled;
        }
    }

    if(json.contains("discovery")) {
        const auto &discovery = json.at("discovery");
        assignIfPresent(discovery, "enabled", config.discovery.enabled);
        assignIfPresent(discovery, "service_type", config.discovery.serviceType);
        assignIfPresent(discovery, "announcement_interval_sec", config.discovery.announcementIntervalSec);
    }

    if(json.contains("synthetic_input")) {
        const auto &synthetic = json.at("synthetic_input");
        assignIfPresent(synthetic, "enabled", config.syntheticInput.enabled);
        assignIfPresent(synthetic, "use_when_no_camera", config.syntheticInput.useWhenNoCamera);
        assignIfPresent(synthetic, "force_no_camera", config.syntheticInput.forceNoCamera);
        assignIfPresent(synthetic, "depth_scale", config.syntheticInput.depthScale);
    }

    return config;
}

nlohmann::json Config::toJson(const Config &config) {
    return {
        { "instance_id", config.instanceId },
        { "bind_address", config.bindAddress },
        { "http_port", config.httpPort },
        { "log_level", config.logLevel },
        { "camera",
          {
              { "serial_number", config.camera.serialNumber },
              { "auto_open_first_femto_bolt", config.camera.autoOpenFirstFemtoBolt },
              { "enable_global_timestamp", config.camera.enableGlobalTimestamp },
              { "retry_interval_ms", config.camera.retryIntervalMs },
          } },
        { "streams",
          {
              { "color",
                {
                    { "enabled", config.color.enabled },
                    { "width", config.color.width },
                    { "height", config.color.height },
                    { "fps", config.color.fps },
                    { "target_bitrate_mbps", config.color.targetBitrateMbps },
                } },
              { "depth",
                {
                    { "enabled", config.depth.enabled },
                    { "width", config.depth.width },
                    { "height", config.depth.height },
                    { "fps", config.depth.fps },
                    { "align_to_color", config.depth.alignToColor },
                } },
              { "depth_preview",
                {
                    { "enabled", config.depthPreview.enabled },
                    { "target_bitrate_mbps", config.depthPreview.targetBitrateMbps },
                    { "mode", config.depthPreview.mode },
                    { "min_depth_mm", config.depthPreview.minDepthMm },
                    { "max_depth_mm", config.depthPreview.maxDepthMm },
                } },
              { "authoritative_depth",
                {
                    { "enabled", config.depthBinary.enabled },
                    { "compression", config.depthBinary.compression },
                    { "compression_level", config.depthBinary.compressionLevel },
                } },
          } },
        { "discovery",
          {
              { "enabled", config.discovery.enabled },
              { "service_type", config.discovery.serviceType },
              { "announcement_interval_sec", config.discovery.announcementIntervalSec },
          } },
        { "synthetic_input",
          {
              { "enabled", config.syntheticInput.enabled },
              { "use_when_no_camera", config.syntheticInput.useWhenNoCamera },
              { "force_no_camera", config.syntheticInput.forceNoCamera },
              { "depth_scale", config.syntheticInput.depthScale },
          } },
    };
}

Config Config::loadFromArgs(int argc, char **argv) {
    Config config;
    std::optional<std::filesystem::path> configPath;
    std::optional<std::string> serialOverride;
    std::optional<uint16_t> httpPortOverride;
    std::optional<std::string> logLevelOverride;

    for(int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if(arg == "--config" && i + 1 < argc) {
            configPath = argv[++i];
        }
        else if(arg == "--serial" && i + 1 < argc) {
            serialOverride = argv[++i];
        }
        else if(arg == "--http-port" && i + 1 < argc) {
            httpPortOverride = static_cast<uint16_t>(std::stoi(argv[++i]));
        }
        else if(arg == "--log-level" && i + 1 < argc) {
            logLevelOverride = argv[++i];
        }
    }

    if(configPath) {
        config = loadJsonFile(*configPath);
    }

    if(serialOverride) {
        config.camera.serialNumber = *serialOverride;
    }
    if(httpPortOverride) {
        config.httpPort = *httpPortOverride;
    }
    if(logLevelOverride) {
        config.logLevel = *logLevelOverride;
    }

    config.logLevel = getEnvOrDefault("NUC_LOG_LEVEL", config.logLevel);
    const auto httpPort = getEnvOrDefault("NUC_HTTP_PORT", std::to_string(config.httpPort));
    config.httpPort = static_cast<uint16_t>(std::stoi(httpPort));

    return config;
}

}  // namespace femto
