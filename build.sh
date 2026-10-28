#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -eo pipefail
tree=$(realpath "${1:?Usage: build.sh TREE DEVICE VARIANT [make arguments...]}")
device=${2:?}; variant=${3:?}; shift 3
case "$device:$variant" in
    fuxi:user) out=out-user-release; lock=.fuxi-build.lock ;;
    fuxi:userdebug) out=out; lock=.fuxi-build.lock ;;
    sheng:user) out=out-sheng-user; lock=.sheng-build.lock ;;
    sheng:userdebug) out=out-sheng-userdebug; lock=.sheng-build.lock ;;
    *) printf 'Unsupported product: %s %s\n' "$device" "$variant" >&2; exit 1 ;;
esac
cd "$tree"
out=${OUT_DIR:-$out}
case "$out" in
    /*|..|../*|*/../*|*/..|.) printf 'OUT_DIR must stay relative to the checkout: %s\n' "$out" >&2; exit 1 ;;
esac
exec 9>"$lock"
flock -n 9
export OUT_DIR="$out"
export TARGET_PRODUCT="aospa_$device" TARGET_RELEASE=cp2a TARGET_BUILD_VARIANT="$variant"
export AOSPA_BUILD="$device" BUILD_USERNAME=nobody BUILD_HOSTNAME=android-build
# BUILD_NUMBER is supplied by release automation or Android build defaults.
source build/envsetup.sh
set_stuff_for_environment
if [ "$device" = fuxi ]; then
    # Qualcomm's Android module rules consume this directory. Keep a separate
    # prepared kernel for each Android output instead of writing a shared tree.
    export KERNEL_PREBUILT_DIR="$OUT_DIR/kernel-prebuilt"
    kernel_out="$tree/$KERNEL_PREBUILT_DIR"
    export PATH="$kernel_out/host/bin:$PATH"
    export LD_LIBRARY_PATH="$kernel_out/host/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    if [ "$variant" = user ]; then
        export LTO=full
    else
        export LTO=thin LZ4_RAMDISK_COMPRESS_ARGS=--fast
    fi
    ANDROID_KERNEL_OUT="$kernel_out" KERNEL_VARIANT=gki \
        bash kernel_platform/build/android/prepare_vendor.sh kalama gki "$tree/$OUT_DIR/kernel-platform"
fi
if [ "$#" -eq 0 ]; then set -- target-files-package; fi
m "$@"
