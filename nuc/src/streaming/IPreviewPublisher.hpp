#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

namespace femto {

class IPreviewPublisher {
public:
    using FrameCallback = std::function<void(std::shared_ptr<const std::vector<uint8_t>>, uint64_t, double)>;

    virtual ~IPreviewPublisher() = default;

    virtual bool start(int width, int height, int fps, int quality = 85) = 0;
    virtual void stop() = 0;
    virtual bool running() const = 0;
    virtual bool pushRgbFrame(const uint8_t *data, std::size_t bytes, uint64_t timestampUs) = 0;
    virtual bool pushJpegFrame(std::shared_ptr<const std::vector<uint8_t>> jpeg, uint64_t timestampUs) = 0;
    virtual std::shared_ptr<const std::vector<uint8_t>> latestJpeg() const = 0;
    virtual void setFrameCallback(FrameCallback callback) = 0;
};

// TODO(WebRTC): add a WebRtcPreviewPublisher implementing this interface using a
// GStreamer pipeline such as:
// appsrc ! videoconvert ! queue leaky=downstream max-size-buffers=2 !
// x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 !
// rtph264pay config-interval=-1 pt=96 ! webrtcbin

}  // namespace femto
