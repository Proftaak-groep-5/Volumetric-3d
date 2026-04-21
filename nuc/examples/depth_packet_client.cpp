#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>
#include <zstd.h>

#pragma pack(push, 1)
struct DepthPacketPrefix {
    uint8_t magic[4];
    uint16_t schema_version;
    uint16_t flags;
    uint32_t header_json_bytes;
    uint32_t payload_bytes;
};
#pragma pack(pop)

static_assert(sizeof(DepthPacketPrefix) == 16, "Unexpected packet prefix size");

int main() {
    // Replace this with bytes received from your preferred WebSocket client library.
    std::vector<uint8_t> message;

    if(message.size() < sizeof(DepthPacketPrefix)) {
        std::cerr << "No packet bytes loaded\n";
        return 1;
    }

    DepthPacketPrefix prefix {};
    std::memcpy(&prefix, message.data(), sizeof(prefix));
    if(std::memcmp(prefix.magic, "OBD1", 4) != 0) {
        throw std::runtime_error("unexpected packet magic");
    }

    const auto headerOffset = sizeof(DepthPacketPrefix);
    const auto payloadOffset = headerOffset + prefix.header_json_bytes;
    if(message.size() < payloadOffset + prefix.payload_bytes) {
        throw std::runtime_error("packet too short");
    }

    const auto headerText = std::string(reinterpret_cast<const char *>(message.data() + headerOffset), prefix.header_json_bytes);
    const auto header = nlohmann::json::parse(headerText);

    std::vector<uint8_t> depthBytes(header.at("uncompressed_byte_size").get<std::size_t>());
    const auto status = ZSTD_decompress(depthBytes.data(), depthBytes.size(), message.data() + payloadOffset, prefix.payload_bytes);
    if(ZSTD_isError(status)) {
        throw std::runtime_error(ZSTD_getErrorName(status));
    }

    const auto *depth16 = reinterpret_cast<const uint16_t *>(depthBytes.data());
    std::cout << "frame=" << header.at("frame_index")
              << " size=" << header.at("width") << "x" << header.at("height")
              << " depth_scale=" << header.at("depth_scale")
              << " first_pixel=" << depth16[0] << "\n";
    return 0;
}
