#pragma once

#include "config/Config.hpp"
#include "util/StatsCollector.hpp"

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

namespace femto {

class OrbbecCamera {
public:
    struct FrameEnvelope {
        std::vector<uint8_t> bytes;
        std::shared_ptr<const std::vector<uint8_t>> jpegBytes;
        int width = 0;
        int height = 0;
        uint64_t timestampUs = 0;
        uint64_t systemTimestampUs = 0;
        uint64_t frameIndex = 0;
        std::string format;
    };

    struct DepthEnvelope {
        std::vector<uint16_t> values;
        int width = 0;
        int height = 0;
        uint64_t timestampUs = 0;
        uint64_t systemTimestampUs = 0;
        uint64_t frameIndex = 0;
        std::string format;
        float depthScale = 1.0f;
    };

    using ColorCallback = std::function<void(const FrameEnvelope &)>;
    using DepthCallback = std::function<void(const DepthEnvelope &)>;

    OrbbecCamera(Config &config, StatsCollector &stats);
    ~OrbbecCamera();

    void start();
    void stop();
    void requestReconnect();
    void requestRestartStreams();

    void setColorCallback(ColorCallback callback);
    void setDepthCallback(DepthCallback callback);

    nlohmann::json metadataJson() const;
    nlohmann::json capabilitiesJson() const;
    nlohmann::json settingsJson() const;
    RuntimeSettings runtimeSettings() const;

    nlohmann::json applySettings(const nlohmann::json &patch);
    std::optional<FrameEnvelope> latestColorFrame() const;
    std::optional<DepthEnvelope> latestDepthFrame() const;

    bool connected() const;
    std::string cameraSerial() const;
    std::string cameraName() const;
    std::string lastError() const;

private:
    void workerLoop();
    void disconnectLocked();
    bool connectLocked();
    void captureOnce();
    void rebuildMetadataLocked();
    void rebuildCapabilitiesLocked();

    struct Impl;
    std::unique_ptr<Impl> impl_;

    Config &config_;
    StatsCollector &stats_;
    mutable std::mutex mutex_;
    RuntimeSettings runtimeSettings_;
    nlohmann::json metadata_;
    nlohmann::json capabilities_;
    std::optional<FrameEnvelope> latestColorFrame_;
    std::optional<DepthEnvelope> latestDepthFrame_;
    ColorCallback colorCallback_;
    DepthCallback depthCallback_;
    std::thread worker_;
    std::atomic<bool> running_{ false };
    std::atomic<bool> reconnectRequested_{ false };
    std::atomic<bool> restartRequested_{ false };
    std::chrono::steady_clock::time_point lastNoCameraLog_{};
    std::string lastError_;
    bool connected_ = false;
    int consecutiveFrameTimeouts_ = 0;
};

}  // namespace femto
