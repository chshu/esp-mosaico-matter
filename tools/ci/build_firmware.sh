#!/usr/bin/env bash
# Build on a clean checkout; Board Manager generates files in the example.
set -euo pipefail
variant=${1:?Usage: build_firmware.sh matter_hub_claw|matter_hub_no_agent|matter_hub_xiaozhi|matter_bridge|matter_bridge_irisfw}
case "$variant" in
    matter_hub_claw|matter_hub_no_agent|matter_hub_xiaozhi) application=matter_hub ;;
    matter_bridge|matter_bridge_irisfw) application=matter_bridge ;;
    *) echo "Unsupported firmware: $variant" >&2; exit 1 ;;
esac
: "${IDF_PATH:?Source ESP-IDF export.sh first}"
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
project_dir="$repo_dir/examples/$application"
output_dir="$repo_dir/build/firmware/images"
mkdir -p "$output_dir"
cd "$project_dir"
idf.py bmgr -c "boards;../../third_party/esp-mosaico-claw/boards" -b esp_mosaico
# Select the hub agent as the noninteractive equivalent of menuconfig.
# Board Manager applies the board overlay as it does in the example README.
if [ "$application" = matter_hub ]; then
    agent=${variant#matter_hub_}
    config="$repo_dir/build/firmware/$variant.sdkconfig"
    printf 'CONFIG_APP_MATTER_HUB_%s=y\n' "$(echo "$agent" | tr '[:lower:]' '[:upper:]')" > "$config"
    export SDKCONFIG_DEFAULTS="$project_dir/sdkconfig.defaults;$config"
fi
if [ "$variant" = matter_bridge_irisfw ]; then
    utils="$repo_dir/build/irisfw-utils"
    utils_revision=$(cat "$repo_dir/tools/ci/irisfw-utils-revision.txt")
    if [ ! -d "$utils/.git" ]; then
        git init "$utils"
        git -C "$utils" remote add origin https://github.com/esp-mosaico/esp-mosaico-utils.git
    fi
    git -C "$utils" fetch --depth 1 origin "$utils_revision"
    git -C "$utils" checkout --detach "$utils_revision"
    python "$repo_dir/tools/ci/release_irisfw.py" --project "$project_dir" --utils "$utils"
    cp build-irisfw/matter_bridge-system-update.irisfw "$output_dir/"
    cp build-irisfw/matter_bridge-system-update.irisfw.sha256 "$output_dir/"
    cp "$repo_dir/tools/ci/irisfw-utils-revision.txt" "$output_dir/matter_bridge_irisfw-utils.txt"
else
    idf.py build
    idf.py merge-bin -o "$output_dir/$variant.bin"
fi
{
    printf 'esp-mosaico-matter: %s\n' "$(git -C "$repo_dir" rev-parse HEAD)"
    printf 'esp-idf: %s\n' "$(git -C "$IDF_PATH" rev-parse HEAD)"
    git -C "$repo_dir" submodule status --recursive
} > "$output_dir/$variant.txt"
