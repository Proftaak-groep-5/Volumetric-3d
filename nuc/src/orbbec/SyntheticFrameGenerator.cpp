#include "orbbec/SyntheticFrameGenerator.hpp"

#include "util/Log.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <ctime>
#include <exception>

namespace femto {
namespace {

uint8_t triangleWave(int value) {
    value %= 510;
    if(value < 0) {
        value += 510;
    }
    return static_cast<uint8_t>(value <= 255 ? value : 510 - value);
}

}  // namespace

SyntheticFrameGenerator::SyntheticFrameGenerator(const Config &config) : config_(config) {}

SyntheticFrameGenerator::~SyntheticFrameGenerator() {
    stop();
}

void SyntheticFrameGenerator::start(std::function<bool()> activeProvider) {
    if(running_.exchange(true)) {
        return;
    }
    activeProvider_ = std::move(activeProvider);
    worker_ = std::thread([this] {
        while(running_) {
            try {
                workerLoop();
            }
            catch(const std::exception &ex) {
                active_ = false;
                log::get()->error("event=synthetic_source state=crashed error=\"{}\" action=retry", ex.what());
            }
            catch(...) {
                active_ = false;
                log::get()->error("event=synthetic_source state=crashed error=unknown action=retry");
            }
            if(running_) {
                std::this_thread::sleep_for(std::chrono::seconds(1));
            }
        }
    });
}

void SyntheticFrameGenerator::stop() {
    if(!running_.exchange(false)) {
        return;
    }
    if(worker_.joinable()) {
        worker_.join();
    }
    active_ = false;
}

void SyntheticFrameGenerator::setColorCallback(ColorCallback callback) {
    std::scoped_lock lock(mutex_);
    colorCallback_ = std::move(callback);
}

void SyntheticFrameGenerator::setDepthCallback(DepthCallback callback) {
    std::scoped_lock lock(mutex_);
    depthCallback_ = std::move(callback);
}

std::optional<OrbbecCamera::FrameEnvelope> SyntheticFrameGenerator::latestColorFrame() const {
    std::scoped_lock lock(mutex_);
    return latestColorFrame_;
}

std::optional<OrbbecCamera::DepthEnvelope> SyntheticFrameGenerator::latestDepthFrame() const {
    std::scoped_lock lock(mutex_);
    return latestDepthFrame_;
}

bool SyntheticFrameGenerator::active() const {
    return active_.load();
}

void SyntheticFrameGenerator::workerLoop() {
    auto nextColorAt = std::chrono::steady_clock::now();
    auto nextDepthAt = nextColorAt;
    bool loggedActive = false;

    while(running_) {
        const bool shouldGenerate = activeProvider_ ? activeProvider_() : false;
        if(!shouldGenerate) {
            if(loggedActive) {
                log::get()->info("event=synthetic_source state=inactive");
                loggedActive = false;
            }
            active_ = false;
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            nextColorAt = std::chrono::steady_clock::now();
            nextDepthAt = nextColorAt;
            continue;
        }

        if(!loggedActive) {
            log::get()->warn("event=synthetic_source state=active reason=no_camera_or_forced");
            loggedActive = true;
        }
        active_ = true;

        const auto now = std::chrono::steady_clock::now();
        const auto colorInterval = std::chrono::microseconds(1'000'000 / std::max(1, config_.color.fps));
        const auto depthInterval = std::chrono::microseconds(1'000'000 / std::max(1, config_.depth.fps));
        bool emitted = false;
        const auto frameIndex = ++frameCounter_;

        if(now >= nextColorAt) {
            auto frame = makeColorFrame(frameIndex);
            ColorCallback callback;
            {
                std::scoped_lock lock(mutex_);
                latestColorFrame_ = frame;
                callback = colorCallback_;
            }
            if(callback) {
                callback(frame);
            }
            nextColorAt = now + colorInterval;
            emitted = true;
        }

        if(now >= nextDepthAt) {
            auto frame = makeDepthFrame(frameIndex);
            DepthCallback callback;
            {
                std::scoped_lock lock(mutex_);
                latestDepthFrame_ = frame;
                callback = depthCallback_;
            }
            if(callback) {
                callback(frame);
            }
            nextDepthAt = now + depthInterval;
            emitted = true;
        }

        if(!emitted) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
}

OrbbecCamera::FrameEnvelope SyntheticFrameGenerator::makeColorFrame(uint64_t frameIndex) const {
    OrbbecCamera::FrameEnvelope frame;
    frame.width = config_.color.width;
    frame.height = config_.color.height;
    frame.timestampUs = steadyTimestampUs();
    frame.systemTimestampUs = systemTimestampUs();
    frame.frameIndex = frameIndex;
    frame.format = "RGB";
    frame.bytes.resize(static_cast<std::size_t>(frame.width) * static_cast<std::size_t>(frame.height) * 3);

    for(int y = 0; y < frame.height; ++y) {
        for(int x = 0; x < frame.width; ++x) {
            const auto index = static_cast<std::size_t>((y * frame.width + x) * 3);
            const int band = (x / std::max(1, frame.width / 8) + static_cast<int>(frameIndex % 8)) % 8;
            frame.bytes[index + 0] = triangleWave(x + static_cast<int>(frameIndex * 2));
            frame.bytes[index + 1] = triangleWave(y + static_cast<int>(frameIndex * 3));
            frame.bytes[index + 2] = static_cast<uint8_t>(band * 32);
        }
    }

    return frame;
}

OrbbecCamera::DepthEnvelope SyntheticFrameGenerator::makeDepthFrame(uint64_t frameIndex) const {
    OrbbecCamera::DepthEnvelope frame;
    frame.width = config_.depth.width;
    frame.height = config_.depth.height;
    frame.timestampUs = steadyTimestampUs();
    frame.systemTimestampUs = systemTimestampUs();
    frame.frameIndex = frameIndex;
    frame.format = "Z16";
    frame.depthScale = config_.syntheticInput.depthScale;
    frame.values.resize(static_cast<std::size_t>(frame.width) * static_cast<std::size_t>(frame.height));

    for(int y = 0; y < frame.height; ++y) {
        for(int x = 0; x < frame.width; ++x) {
            const auto index = static_cast<std::size_t>(y * frame.width + x);
            const uint16_t gradient = static_cast<uint16_t>(800 + (3200 * x) / std::max(1, frame.width - 1));
            const uint16_t wave = static_cast<uint16_t>((y * 17 + static_cast<int>(frameIndex * 13)) % 600);
            uint16_t value = static_cast<uint16_t>(std::min<uint32_t>(65535u, static_cast<uint32_t>(gradient) + static_cast<uint32_t>(wave)));
            if(((x / 32) + (y / 32) + static_cast<int>(frameIndex / 15)) % 11 == 0) {
                value = 0;
            }
            frame.values[index] = value;
        }
    }

    return frame;
}

uint64_t SyntheticFrameGenerator::steadyTimestampUs() {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                                     std::chrono::steady_clock::now().time_since_epoch())
                                     .count());
}

uint64_t SyntheticFrameGenerator::systemTimestampUs() {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                                     std::chrono::system_clock::now().time_since_epoch())
                                     .count());
}

}  // namespace femto
