# Xiaomi SM8550 platform configuration

Shared by `fuxi` and `sheng`.

- `BoardConfigCommon.mk`: architecture, boot image format, common AVB settings,
  recovery, WLAN and shared policy search paths.
- `common.mk`: common product packages, permissions and platform defaults.
- `configs/`: identical audio policy, hotword permissions and framework matrix.
- `sepolicy/`: rules shared by both device variants.

Each variant sets `SM8550_VARIANT_PATH` before including these files. Its own
configuration keeps partition sizes, init implementation, sensor capabilities,
firmware-dependent settings, feature packages and proprietary inputs.

The platform layer is checked out at `device/xiaomi/sm8550-platform-common`
in both source trees. Changes are maintained together in this repository.
