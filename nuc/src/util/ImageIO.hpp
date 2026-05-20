#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace femto::imageio {

struct RgbImage {
    std::vector<uint8_t> bytes;
    int width = 0;
    int height = 0;
};

std::shared_ptr<const std::vector<uint8_t>> encodeRgbJpeg(const uint8_t *rgb, int width, int height, int quality = 90);
std::shared_ptr<const std::vector<uint8_t>> encodeGray16Png(const uint16_t *depth, int width, int height);
std::optional<RgbImage> decodeJpegToRgb(const uint8_t *jpeg, std::size_t bytes);

bool writeRgbJpegFile(const std::filesystem::path &path, const uint8_t *rgb, int width, int height, int quality = 90);
bool writeGray16PngFile(const std::filesystem::path &path, const uint16_t *depth, int width, int height);

}  // namespace femto::imageio
