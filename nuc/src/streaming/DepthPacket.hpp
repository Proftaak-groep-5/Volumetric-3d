#pragma once

#include <array>
#include <cstdint>

namespace femto::depth_packet {

inline constexpr std::array<uint8_t, 4> kMagic { 'O', 'B', 'D', '1' };
inline constexpr uint16_t kSchemaVersion = 1;
inline constexpr uint16_t kFlagsNone = 0;

#pragma pack(push, 1)
struct Prefix {
    uint8_t magic[4];
    uint16_t schemaVersion;
    uint16_t flags;
    uint32_t headerJsonBytes;
    uint32_t payloadBytes;
};
#pragma pack(pop)

static_assert(sizeof(Prefix) == 16, "Depth packet prefix must stay 16 bytes.");

}  // namespace femto::depth_packet
