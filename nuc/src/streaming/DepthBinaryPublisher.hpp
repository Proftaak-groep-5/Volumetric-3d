#pragma once

#include "config/Config.hpp"
#include "streaming/DepthPacket.hpp"
#include "util/StatsCollector.hpp"

#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace femto {

class DepthBinaryPublisher {
public:
    using PacketCallback = std::function<void(std::shared_ptr<const std::vector<uint8_t>>)>;

    DepthBinaryPublisher(Config &config, StatsCollector &stats);
    ~DepthBinaryPublisher();

    void publishFrame(const std::vector<uint16_t> &values, int width, int height, uint64_t frameIndex, uint64_t timestampUs, uint64_t systemTimestampUs,
                      float depthScale, const nlohmann::json &intrinsicsRef, const std::string &pixelFormat);

    std::shared_ptr<const std::vector<uint8_t>> latestPacket() const;
    void setPacketCallback(PacketCallback callback);

private:
    Config &config_;
    StatsCollector &stats_;
    mutable std::mutex mutex_;
    std::shared_ptr<const std::vector<uint8_t>> latestPacket_;
    PacketCallback callback_;
    struct ZstdContext;
    std::unique_ptr<ZstdContext> zstd_;
    std::chrono::steady_clock::time_point lastLogAt_{};
    uint64_t windowFrames_ = 0;
    uint64_t windowBytes_ = 0;
    uint64_t windowRawBytes_ = 0;
};

}  // namespace femto
