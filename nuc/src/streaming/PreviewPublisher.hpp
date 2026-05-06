#pragma once

#include "streaming/IPreviewPublisher.hpp"

#include <cstdint>
#include <chrono>
#include <memory>
#include <mutex>
#include <string>

namespace femto {

class PreviewPublisher : public IPreviewPublisher {
public:
    explicit PreviewPublisher(std::string name);
    ~PreviewPublisher() override;

    bool start(int width, int height, int fps, int quality = 85) override;
    void stop() override;
    bool running() const override;

    bool pushRgbFrame(const uint8_t *data, std::size_t bytes, uint64_t timestampUs) override;
    std::shared_ptr<const std::vector<uint8_t>> latestJpeg() const override;
    void setFrameCallback(FrameCallback callback) override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    std::string name_;
    mutable std::mutex mutex_;
    std::shared_ptr<const std::vector<uint8_t>> latestJpeg_;
    FrameCallback callback_;
};

}  // namespace femto
