#pragma once

#include "config/Config.hpp"
#include "orbbec/OrbbecCamera.hpp"

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <thread>

namespace femto {

class SyntheticFrameGenerator {
public:
    using ColorCallback = OrbbecCamera::ColorCallback;
    using DepthCallback = OrbbecCamera::DepthCallback;

    explicit SyntheticFrameGenerator(const Config &config);
    ~SyntheticFrameGenerator();

    void start(std::function<bool()> activeProvider);
    void stop();

    void setColorCallback(ColorCallback callback);
    void setDepthCallback(DepthCallback callback);

    std::optional<OrbbecCamera::FrameEnvelope> latestColorFrame() const;
    std::optional<OrbbecCamera::DepthEnvelope> latestDepthFrame() const;
    bool active() const;

private:
    void workerLoop();
    OrbbecCamera::FrameEnvelope makeColorFrame(uint64_t frameIndex) const;
    OrbbecCamera::DepthEnvelope makeDepthFrame(uint64_t frameIndex) const;
    static uint64_t steadyTimestampUs();
    static uint64_t systemTimestampUs();

    const Config &config_;
    std::function<bool()> activeProvider_;
    mutable std::mutex mutex_;
    ColorCallback colorCallback_;
    DepthCallback depthCallback_;
    std::optional<OrbbecCamera::FrameEnvelope> latestColorFrame_;
    std::optional<OrbbecCamera::DepthEnvelope> latestDepthFrame_;
    std::thread worker_;
    std::atomic<bool> running_{ false };
    std::atomic<bool> active_{ false };
    std::atomic<uint64_t> frameCounter_{ 0 };
};

}  // namespace femto
