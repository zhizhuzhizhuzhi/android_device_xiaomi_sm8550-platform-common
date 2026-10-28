# Xiaomi SM8550 platform configuration

Shared AOSPA Calcite configuration for Xiaomi 13 (`fuxi`) and Pad 6S Pro (`sheng`).
Device and device-family configuration live in their own repositories. This tree
contains the common build flags, permissions, audio policy and input tooling.

## Checkout and preparation

Use the pinned manifests in [android_local_manifests](https://github.com/zhizhuzhizhuzhi/android_local_manifests).
The manifests directly pin each modified source project. Binary prerequisites
and extraction commands are documented in the selected device repository.

## Build

From the prepared Android root, use the same entry for either product:

```sh
bash build-device.sh fuxi user -j8 target-files-package
bash build-device.sh sheng userdebug -j8 target-files-package
```

| Product | Default output |
| --- | --- |
| fuxi user | out-user-release |
| fuxi userdebug | out |
| sheng user | out-sheng-user |
| sheng userdebug | out-sheng-userdebug |

The wrapper selects `aospa_<device>`, release `cp2a`, and the requested variant.
It uses the checked-in AOSPA environment and prepares the Fuxi source kernel before
Android compilation. It does not sync repositories, fetch dependencies or apply
source patches. Do not replace it with a plain `m` command before preparing the
Fuxi kernel. `OUT_DIR` accepts another checkout-relative directory.

`BUILD_NUMBER` is optional and supplied by the caller for reproducible releases;
there is no hard-coded release date. Android chooses its default when unset.
The wrapper takes a nonblocking per-device build lock, with no polling/retry loop.

`tools/extract-device-inputs.py` validates the per-device input manifests and
`shared-inputs.json`. Closed binaries and signing keys are not stored here.
