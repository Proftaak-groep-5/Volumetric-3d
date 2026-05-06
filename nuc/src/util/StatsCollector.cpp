#include "util/StatsCollector.hpp"

#include <algorithm>

namespace femto {

StatsCollector::StatsCollector() : startedAt_(std::chrono::steady_clock::now()) {}

void StatsCollector::onColorInputFrame() {
    ++colorInputFrames_;
}

void StatsCollector::onDepthInputFrame() {
    ++depthInputFrames_;
}

void StatsCollector::onColorPreviewFrame(std::size_t bytes, double encodeMs) {
    ++colorPreviewFrames_;
    colorPreviewBytes_ += static_cast<uint64_t>(bytes);
    ++encodeSamples_;
    encodeMicrosTotal_ += static_cast<uint64_t>(encodeMs * 1000.0);
}

void StatsCollector::onDepthPreviewFrame(std::size_t bytes, double encodeMs) {
    ++depthPreviewFrames_;
    depthPreviewBytes_ += static_cast<uint64_t>(bytes);
    ++encodeSamples_;
    encodeMicrosTotal_ += static_cast<uint64_t>(encodeMs * 1000.0);
}

void StatsCollector::onDepthBinaryFrame(std::size_t bytes, std::size_t rawBytes, double compressMs) {
    ++depthBinaryFrames_;
    depthBinaryBytes_ += static_cast<uint64_t>(bytes);
    depthBinaryFrameBytesTotal_ += static_cast<uint64_t>(bytes);
    depthBinaryRawBytes_ += static_cast<uint64_t>(rawBytes);
    ++compressSamples_;
    compressMicrosTotal_ += static_cast<uint64_t>(compressMs * 1000.0);
}

void StatsCollector::onDroppedInputFrame() {
    ++droppedInputFrames_;
}

void StatsCollector::onDroppedOutputFrame() {
    ++droppedOutputFrames_;
}

uint64_t StatsCollector::uptimeSeconds() const {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - startedAt_).count());
}

nlohmann::json StatsCollector::snapshot() const {
    const auto uptime = std::max<uint64_t>(1, uptimeSeconds());
    const auto encodeSamples = std::max<uint64_t>(1, encodeSamples_.load());
    const auto compressSamples = std::max<uint64_t>(1, compressSamples_.load());
    return {
        { "uptime_sec", uptime },
        { "input_fps_color", static_cast<double>(colorInputFrames_.load()) / static_cast<double>(uptime) },
        { "input_fps_depth", static_cast<double>(depthInputFrames_.load()) / static_cast<double>(uptime) },
        { "output_fps_color_preview", static_cast<double>(colorPreviewFrames_.load()) / static_cast<double>(uptime) },
        { "output_fps_depth_preview", static_cast<double>(depthPreviewFrames_.load()) / static_cast<double>(uptime) },
        { "depth_binary_fps", static_cast<double>(depthBinaryFrames_.load()) / static_cast<double>(uptime) },
        { "average_encode_latency_ms", static_cast<double>(encodeMicrosTotal_.load()) / 1000.0 / static_cast<double>(encodeSamples) },
        { "average_depth_compress_latency_ms", static_cast<double>(compressMicrosTotal_.load()) / 1000.0 / static_cast<double>(compressSamples) },
        { "average_depth_binary_frame_size_bytes",
          depthBinaryFrames_.load() == 0 ? 0.0 : static_cast<double>(depthBinaryFrameBytesTotal_.load()) / static_cast<double>(depthBinaryFrames_.load()) },
        { "depth_binary_compression_ratio",
          depthBinaryBytes_.load() == 0 ? 0.0 : static_cast<double>(depthBinaryRawBytes_.load()) / static_cast<double>(depthBinaryBytes_.load()) },
        { "dropped_input_frames", droppedInputFrames_.load() },
        { "dropped_output_frames", droppedOutputFrames_.load() },
        { "network_throughput_estimate_mbps",
          (static_cast<double>(colorPreviewBytes_.load() + depthPreviewBytes_.load() + depthBinaryBytes_.load()) * 8.0) / 1'000'000.0 /
              static_cast<double>(uptime) },
        { "depth_binary_payload_throughput_mbps",
          (static_cast<double>(depthBinaryRawBytes_.load()) * 8.0) / 1'000'000.0 / static_cast<double>(uptime) },
        { "depth_binary_transport_throughput_mbps",
          (static_cast<double>(depthBinaryBytes_.load()) * 8.0) / 1'000'000.0 / static_cast<double>(uptime) },
        { "cpu_usage_estimate", nullptr },
        { "memory_usage_estimate", nullptr },
        { "queue_depths", { { "preview", 0 }, { "depth_binary", 0 } } },
        { "pipeline_latency_estimate_ms", nullptr },
    };
}

}  // namespace femto
