#pragma once

#include <string>
#include <vector>

namespace femto::net {

std::vector<std::string> localIpv4Addresses();
std::string firstReachableIpv4();

}  // namespace femto::net
