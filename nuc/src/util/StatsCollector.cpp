#include "util/StatsCollector.hpp"

#include <algorithm>
#include <iterator>

namespace femto {
namespace {

constexpr auto kFpsRollingWindow = std::chrono::seconds(5);
constexpr auto kFpsInstantWindow = std::chrono::seconds(1);
constexpr auto kMaxTrackedRateWindow = std::chrono::seconds(6);

}  // namespace

StatsCollector::StatsCollector() : startedAt_(std::chrono::steady_clock::now()) {}

void StatsCollector::onColorInputFrame() {
    ++colorInputFrames_;
    recordEvent(colorInputRateWindow_);
}

void StatsCollector::onDepthInputFrame() {
    ++depthInputFrames_;
    recordEvent(depthInputRateWindow_);
}

void StatsCollector::onColorPreviewFrame(std::size_t bytes, double encodeMs) {
    ++colorPreviewFrames_;
    recordEvent(colorPreviewRateWindow_);
    colorPreviewBytes_ += static_cast<uint64_t>(bytes);
    ++encodeSamples_;
    encodeMicrosTotal_ += static_cast<uint64_t>(encodeMs * 1000.0);
}

void StatsCollector::onDepthPreviewFrame(std::size_t bytes, double encodeMs) {
    ++depthPreviewFrames_;
    recordEvent(depthPreviewRateWindow_);
    depthPreviewBytes_ += static_cast<uint64_t>(bytes);
    ++encodeSamples_;
    encodeMicrosTotal_ += static_cast<uint64_t>(encodeMs * 1000.0);
}

void StatsCollector::onDepthBinaryFrame(std::size_t bytes, std::size_t rawBytes, double compressMs) {
    ++depthBinaryFrames_;
    recordEvent(depthBinaryRateWindow_);
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

void StatsCollector::recordEvent(RollingRateWindow &window) {
    const auto now = std::chrono::steady_clock::now();
    std::scoped_lock lock(window.mutex);
    window.events.push_back(now);
    pruneEvents(window.events, now - kMaxTrackedRateWindow);
}

double StatsCollector::rollingRate(const RollingRateWindow &window, std::chrono::steady_clock::time_point now,
                                   std::chrono::steady_clock::duration windowDuration) const {
    if(windowDuration <= std::chrono::steady_clock::duration::zero()) {
        return 0.0;
    }

    std::scoped_lock lock(window.mutex);
    pruneEvents(window.events, now - kMaxTrackedRateWindow);
    if(window.events.empty()) {
        return 0.0;
    }

    const auto windowStart = now - windowDuration;
    const auto firstInWindow = std::lower_bound(window.events.begin(), window.events.end(), windowStart);
    const auto count = static_cast<double>(std::distance(firstInWindow, window.events.end()));
    const auto seconds = std::chrono::duration<double>(windowDuration).count();
    if(seconds <= 0.0) {
        return 0.0;
    }
    return count / seconds;
}

void StatsCollector::pruneEvents(std::deque<std::chrono::steady_clock::time_point> &events, std::chrono::steady_clock::time_point cutoff) {
    while(!events.empty() && events.front() < cutoff) {
        events.pop_front();
    }
}

nlohmann::json StatsCollector::snapshot() const {
    const auto uptime = std::max<uint64_t>(1, uptimeSeconds());
    const auto encodeSamples = std::max<uint64_t>(1, encodeSamples_.load());
    const auto compressSamples = std::max<uint64_t>(1, compressSamples_.load());
    const auto now = std::chrono::steady_clock::now();

    const auto inputFpsColorRolling = rollingRate(colorInputRateWindow_, now, kFpsRollingWindow);
    const auto inputFpsDepthRolling = rollingRate(depthInputRateWindow_, now, kFpsRollingWindow);
    const auto outputFpsColorRolling = rollingRate(colorPreviewRateWindow_, now, kFpsRollingWindow);
    const auto outputFpsDepthRolling = rollingRate(depthPreviewRateWindow_, now, kFpsRollingWindow);
    const auto depthBinaryFpsRolling = rollingRate(depthBinaryRateWindow_, now, kFpsRollingWindow);

    const auto inputFpsColorInstant = rollingRate(colorInputRateWindow_, now, kFpsInstantWindow);
    const auto inputFpsDepthInstant = rollingRate(depthInputRateWindow_, now, kFpsInstantWindow);
    const auto outputFpsColorInstant = rollingRate(colorPreviewRateWindow_, now, kFpsInstantWindow);
    const auto outputFpsDepthInstant = rollingRate(depthPreviewRateWindow_, now, kFpsInstantWindow);
    const auto depthBinaryFpsInstant = rollingRate(depthBinaryRateWindow_, now, kFpsInstantWindow);

    const auto inputFpsColorLifetime = static_cast<double>(colorInputFrames_.load()) / static_cast<double>(uptime);
    const auto inputFpsDepthLifetime = static_cast<double>(depthInputFrames_.load()) / static_cast<double>(uptime);
    const auto outputFpsColorLifetime = static_cast<double>(colorPreviewFrames_.load()) / static_cast<double>(uptime);
    const auto outputFpsDepthLifetime = static_cast<double>(depthPreviewFrames_.load()) / static_cast<double>(uptime);
    const auto depthBinaryFpsLifetime = static_cast<double>(depthBinaryFrames_.load()) / static_cast<double>(uptime);

    return {
        { "uptime_sec", uptime },
        { "fps_window_sec", static_cast<int>(kFpsRollingWindow.count()) },
        { "input_fps_color", inputFpsColorRolling },
        { "input_fps_depth", inputFpsDepthRolling },
        { "output_fps_color_preview", outputFpsColorRolling },
        { "output_fps_depth_preview", outputFpsDepthRolling },
        { "depth_binary_fps", depthBinaryFpsRolling },
        { "input_fps_color_1s", inputFpsColorInstant },
        { "input_fps_depth_1s", inputFpsDepthInstant },
        { "output_fps_color_preview_1s", outputFpsColorInstant },
        { "output_fps_depth_preview_1s", outputFpsDepthInstant },
        { "depth_binary_fps_1s", depthBinaryFpsInstant },
        { "input_fps_color_lifetime", inputFpsColorLifetime },
        { "input_fps_depth_lifetime", inputFpsDepthLifetime },
        { "output_fps_color_preview_lifetime", outputFpsColorLifetime },
        { "output_fps_depth_preview_lifetime", outputFpsDepthLifetime },
        { "depth_binary_fps_lifetime", depthBinaryFpsLifetime },
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
