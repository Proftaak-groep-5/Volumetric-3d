#include "streaming/DepthBinaryPublisher.hpp"

#include "streaming/DepthPacket.hpp"
#include "util/Log.hpp"

#include <zstd.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <limits>

namespace femto {

struct DepthBinaryPublisher::ZstdContext {
    ZSTD_CCtx *ctx = ZSTD_createCCtx();

    ~ZstdContext() {
        if(ctx) {
            ZSTD_freeCCtx(ctx);
        }
    }
};

DepthBinaryPublisher::DepthBinaryPublisher(Config &config, StatsCollector &stats) : config_(config), stats_(stats), zstd_(std::make_unique<ZstdContext>()) {}

DepthBinaryPublisher::~DepthBinaryPublisher() = default;

void DepthBinaryPublisher::publishFrame(const std::vector<uint16_t> &values, int width, int height, uint64_t frameIndex, uint64_t timestampUs,
                                        uint64_t systemTimestampUs, float depthScale, const nlohmann::json &intrinsicsRef, const std::string &pixelFormat) {
    if(!config_.depthBinary.enabled || values.empty()) {
        return;
    }
    if(width <= 0 || height <= 0) {
        log::get()->warn("event=depth_binary_drop reason=invalid_dimensions width={} height={}", width, height);
        stats_.onDroppedOutputFrame();
        return;
    }
    const auto expectedSamples = static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
    if(values.size() != expectedSamples) {
        log::get()->warn("event=depth_binary_drop reason=size_mismatch expected_samples={} actual_samples={}", expectedSamples, values.size());
        stats_.onDroppedOutputFrame();
        return;
    }
    if(config_.depthBinary.compression != "zstd") {
        log::get()->warn("event=depth_binary compression={} fallback=zstd", config_.depthBinary.compression);
    }
    if(!zstd_ || !zstd_->ctx) {
        log::get()->error("event=depth_binary_drop reason=no_zstd_context");
        stats_.onDroppedOutputFrame();
        return;
    }

    const auto started = std::chrono::steady_clock::now();
    const auto *source = reinterpret_cast<const uint8_t *>(values.data());
    const auto sourceBytes = values.size() * sizeof(uint16_t);
    if(sourceBytes > static_cast<std::size_t>(std::numeric_limits<uint32_t>::max())) {
        log::get()->error("event=depth_binary_drop reason=raw_frame_too_large bytes={}", sourceBytes);
        stats_.onDroppedOutputFrame();
        return;
    }
    std::vector<uint8_t> compressed(ZSTD_compressBound(sourceBytes));
    const auto compressedBytes = ZSTD_compressCCtx(
        zstd_->ctx, compressed.data(), compressed.size(), source, sourceBytes, std::clamp(config_.depthBinary.compressionLevel, 1, 10));
    if(ZSTD_isError(compressedBytes)) {
        log::get()->error("event=depth_binary_drop reason=compression_failed error={}", ZSTD_getErrorName(compressedBytes));
        stats_.onDroppedOutputFrame();
        return;
    }
    compressed.resize(compressedBytes);
    if(compressed.size() > static_cast<std::size_t>(std::numeric_limits<uint32_t>::max())) {
        log::get()->error("event=depth_binary_drop reason=compressed_frame_too_large bytes={}", compressed.size());
        stats_.onDroppedOutputFrame();
        return;
    }

    const auto header = nlohmann::json{
        { "schema_version", depth_packet::kSchemaVersion },
        { "frame_index", frameIndex },
        { "source_timestamp_us", timestampUs },
        { "system_timestamp_us", systemTimestampUs },
        { "width", width },
        { "height", height },
        { "stride_bytes", width * static_cast<int>(sizeof(uint16_t)) },
        { "pixel_format", pixelFormat },
        { "compression_type", "zstd" },
        { "uncompressed_byte_size", sourceBytes },
        { "compressed_byte_size", compressed.size() },
        { "depth_scale", depthScale },
        { "depth_units", "millimeters = raw * depth_scale" },
        { "invalid_pixel_value", 0 },
        { "intrinsics_reference", intrinsicsRef },
    };
    const auto headerBytes = header.dump();
    if(headerBytes.size() > static_cast<std::size_t>(std::numeric_limits<uint32_t>::max())) {
        log::get()->error("event=depth_binary_drop reason=header_too_large bytes={}", headerBytes.size());
        stats_.onDroppedOutputFrame();
        return;
    }
    auto packet = std::make_shared<std::vector<uint8_t>>();
    packet->reserve(sizeof(depth_packet::Prefix) + headerBytes.size() + compressed.size());
    const depth_packet::Prefix prefix {
        { depth_packet::kMagic[0], depth_packet::kMagic[1], depth_packet::kMagic[2], depth_packet::kMagic[3] },
        depth_packet::kSchemaVersion,
        depth_packet::kFlagsNone,
        static_cast<uint32_t>(headerBytes.size()),
        static_cast<uint32_t>(compressed.size())
    };
    packet->insert(packet->end(), reinterpret_cast<const uint8_t *>(&prefix), reinterpret_cast<const uint8_t *>(&prefix) + sizeof(prefix));
    packet->insert(packet->end(), headerBytes.begin(), headerBytes.end());
    packet->insert(packet->end(), compressed.begin(), compressed.end());

    const double elapsedMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    stats_.onDepthBinaryFrame(packet->size(), sourceBytes, elapsedMs);
    ++windowFrames_;
    windowBytes_ += packet->size();
    windowRawBytes_ += sourceBytes;
    const auto now = std::chrono::steady_clock::now();
    if(lastLogAt_.time_since_epoch().count() == 0) {
        lastLogAt_ = now;
    }
    if(now - lastLogAt_ >= std::chrono::seconds(1)) {
        const auto seconds = std::chrono::duration<double>(now - lastLogAt_).count();
        const auto fps = static_cast<double>(windowFrames_) / seconds;
        const auto avgCompressedBytes = windowFrames_ == 0 ? 0.0 : static_cast<double>(windowBytes_) / static_cast<double>(windowFrames_);
        const auto mbps = (static_cast<double>(windowBytes_) * 8.0) / 1'000'000.0 / seconds;
        const auto rawMbps = (static_cast<double>(windowRawBytes_) * 8.0) / 1'000'000.0 / seconds;
        const auto ratio = windowBytes_ == 0 ? 0.0 : static_cast<double>(windowRawBytes_) / static_cast<double>(windowBytes_);
        log::get()->info("event=depth_binary fps={:.2f} avg_bytes={:.0f} ratio={:.2f} raw_mbps={:.2f} transport_mbps={:.2f}", fps, avgCompressedBytes,
                         ratio, rawMbps, mbps);
        lastLogAt_ = now;
        windowFrames_ = 0;
        windowBytes_ = 0;
        windowRawBytes_ = 0;
    }

    PacketCallback callback;
    {
        std::scoped_lock lock(mutex_);
        latestPacket_ = packet;
        callback = callback_;
    }
    if(callback) {
        callback(packet);
    }
}

std::shared_ptr<const std::vector<uint8_t>> DepthBinaryPublisher::latestPacket() const {
    std::scoped_lock lock(mutex_);
    return latestPacket_;
}

void DepthBinaryPublisher::setPacketCallback(PacketCallback callback) {
    std::scoped_lock lock(mutex_);
    callback_ = std::move(callback);
}

}  // namespace femto
