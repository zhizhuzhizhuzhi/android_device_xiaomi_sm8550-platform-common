#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -eo pipefail
tree=$(cd "$(dirname "$0")" && pwd)
exec bash "$tree/device/xiaomi/sm8550-platform-common/build.sh" "$tree" "$@"
