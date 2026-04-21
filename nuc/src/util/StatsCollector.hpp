#pragma once

#include <atomic>
#include <cstddef>
#include <chrono>
#include <cstdint>

#include <nlohmann/json.hpp>

namespace femto {

class StatsCollector {
public:
    StatsCollector();

    void onColorInputFrame();
    void onDepthInputFrame();
    void onColorPreviewFrame(std::size_t bytes, double encodeMs);
    void onDepthPreviewFrame(std::size_t bytes, double encodeMs);
    void onDepthBinaryFrame(std::size_t bytes, std::size_t rawBytes, double compressMs);
    void onDroppedInputFrame();
    void onDroppedOutputFrame();

    nlohmann::json snapshot() const;
    uint64_t uptimeSeconds() const;

private:
    std::chrono::steady_clock::time_point startedAt_;
    std::atomic<uint64_t> colorInputFrames_{ 0 };
    std::atomic<uint64_t> depthInputFrames_{ 0 };
    std::atomic<uint64_t> colorPreviewFrames_{ 0 };
    std::atomic<uint64_t> depthPreviewFrames_{ 0 };
    std::atomic<uint64_t> depthBinaryFrames_{ 0 };
    std::atomic<uint64_t> droppedInputFrames_{ 0 };
    std::atomic<uint64_t> droppedOutputFrames_{ 0 };
    std::atomic<uint64_t> colorPreviewBytes_{ 0 };
    std::atomic<uint64_t> depthPreviewBytes_{ 0 };
    std::atomic<uint64_t> depthBinaryBytes_{ 0 };
    std::atomic<uint64_t> depthBinaryFrameBytesTotal_{ 0 };
    std::atomic<uint64_t> depthBinaryRawBytes_{ 0 };
    std::atomic<uint64_t> encodeSamples_{ 0 };
    std::atomic<uint64_t> encodeMicrosTotal_{ 0 };
    std::atomic<uint64_t> compressSamples_{ 0 };
    std::atomic<uint64_t> compressMicrosTotal_{ 0 };
};

}  // namespace femto
