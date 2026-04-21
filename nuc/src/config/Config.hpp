#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace femto {

struct PreviewConfig {
    bool enabled = true;
    int width = 1280;
    int height = 720;
    int fps = 15;
    int targetBitrateMbps = 4;
};

struct DepthStreamConfig {
    bool enabled = true;
    int width = 640;
    int height = 576;
    int fps = 15;
    bool alignToColor = false;
};

struct DepthPreviewConfig {
    bool enabled = true;
    int targetBitrateMbps = 2;
    std::string mode = "false_color";
    int minDepthMm = 250;
    int maxDepthMm = 4000;
};

struct DepthBinaryConfig {
    bool enabled = true;
    std::string compression = "zstd";
    int compressionLevel = 3;
};

struct CameraConfig {
    std::string serialNumber;
    bool autoOpenFirstFemtoBolt = true;
    bool enableGlobalTimestamp = true;
    int retryIntervalMs = 2000;
};

struct DiscoveryConfig {
    bool enabled = true;
    std::string serviceType = "urn:orbbec-femtobolt-nuc:service:1";
    int announcementIntervalSec = 30;
};

struct SyntheticInputConfig {
    bool enabled = false;
    bool useWhenNoCamera = true;
    bool forceNoCamera = false;
    float depthScale = 1.0f;
};

struct RuntimeSettings {
    bool colorEnabled = true;
    bool depthPreviewEnabled = true;
    bool depthBinaryEnabled = true;
    bool colorExposureAuto = true;
    std::optional<int> colorExposureValue;
    std::optional<int> colorGain;
    bool colorWhiteBalanceAuto = true;
    std::optional<int> colorWhiteBalanceValue;
    std::optional<int> colorBrightness;
    std::optional<int> colorContrast;
    std::optional<int> colorSaturation;
    std::optional<std::string> depthPreset;
    int depthPreviewMinMm = 250;
    int depthPreviewMaxMm = 4000;
};

struct Config {
    std::string instanceId = "femtobolt-nuc";
    std::string bindAddress = "0.0.0.0";
    uint16_t httpPort = 8080;
    std::string logLevel = "info";
    CameraConfig camera;
    PreviewConfig color;
    DepthStreamConfig depth;
    DepthPreviewConfig depthPreview;
    DepthBinaryConfig depthBinary;
    DiscoveryConfig discovery;
    SyntheticInputConfig syntheticInput;
    RuntimeSettings runtime;

    static Config loadFromArgs(int argc, char **argv);
    static Config fromJson(const nlohmann::json &json);
    static nlohmann::json toJson(const Config &config);
};

}  // namespace femto
