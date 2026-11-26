#!/usr/bin/env python3
"""Build an application's irisfw bundle for ESP-Mosaico retained Recovery."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

TOOLS = Path(__file__).resolve().parent
UTILS_REVISION = (TOOLS / "irisfw-utils-revision.txt").read_text().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True,
                        help="Application directory with an irisfw partition/configuration profile")
    parser.add_argument("--utils", type=Path, required=True,
                        help="esp-mosaico-vibe/submodule/esp-mosaico-utils")
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--release", help="Bundle label; defaults to the built application version")
    parser.add_argument("--sdkconfig-defaults", type=Path, action="append", default=[],
                        help="Additional variant defaults, applied last (repeatable)")
    parser.add_argument("--skip-build", action="store_true",
                        help="Package a previously built irisfw configuration")
    args = parser.parse_args()
    project = args.project.resolve()
    utils = args.utils.resolve()
    build = args.build_dir.resolve() if args.build_dir else project / "build-irisfw"
    partition_csv = project / "partitions_irisfw.csv"
    profile = project / "sdkconfig.irisfw.defaults"
    for path in (partition_csv, profile):
        if not path.is_file():
            parser.error(f"application has no irisfw profile: {path}")
    tools = utils / "mosaico-tools/tools"
    builder = utils / "ESP-Iris/components/esp_iris/tools/system_update_bundle.py"
    revision = subprocess.check_output(
        ["git", "-C", str(utils), "rev-parse", "HEAD"], text=True).strip()
    if revision != UTILS_REVISION:
        parser.error(f"expected utils {UTILS_REVISION}, found {revision}")
    if not args.skip_build:
        board_defaults = project / "components/gen_bmgr_codes/board_manager.defaults"
        if not board_defaults.is_file():
            parser.error("run idf.py bmgr for esp_mosaico before creating a release")
        idf = Path(os.environ["IDF_PATH"]) / "tools/idf.py"
        defaults = [project / "sdkconfig.defaults", board_defaults,
                    utils / "mosaico-tools/components/esp_mosaico_app_recovery/sdkconfig.defaults",
                    TOOLS / "sdkconfig.irisfw.defaults", profile,
                    *(path.resolve() for path in args.sdkconfig_defaults)]
        subprocess.run([
            sys.executable, str(idf), "-C", str(project), "-B", str(build),
            "-D", "IDF_TARGET=esp32s31",
            "-D", f"MOSAICO_IRISFW_UTILS={utils}",
            "-D", f"SDKCONFIG={build / 'sdkconfig'}",
            "-D", "SDKCONFIG_DEFAULTS=" + ";".join(map(str, defaults)),
            "build"], check=True)
    config = json.loads((build / "config/sdkconfig.json").read_text())
    if (config.get("PARTITION_TABLE_OFFSET") != 0x8000 or
            config.get("PARTITION_TABLE_CUSTOM_FILENAME") != "partitions_irisfw.csv" or
            config.get("IDF_TARGET") != "esp32s31" or
            not config.get("ESP_BOARD_ESP_MOSAICO") or
            not config.get("ESP_IRIS_ENABLE") or
            not config.get("ESP_IRIS_TRANSPORT_USB") or
            config.get("ESP_IRIS_RECOVERY_ABI") != 2 or
            config.get("ESP_IRIS_PRODUCT_CONTRACT") != "esp-mosaico/v2" or
            not config.get("ESPTOOLPY_FLASHMODE_QIO") or
            config.get("USB_HS_CONSOLE_USB_CDC_AUTO_INIT")):
        parser.error("build must use the Iris v2 defaults, QIO flash mode and esp32s31 target")
    flash = json.loads((build / "flasher_args.json").read_text())
    description = json.loads((build / "project_description.json").read_text())
    project_name = description["project_name"]
    release = args.release if args.release is not None else description["project_version"]
    stage = build / "system-update"
    table = build / "partition_table/partition-table.bin"
    resources = []
    for label, entry in flash.items():
        if (label not in {"app", "bootloader", "partition-table", "otadata"}
                and isinstance(entry, dict) and "file" in entry):
            resources.extend(["--data", f"{label}={build / entry['file']}"])
    subprocess.run([
        sys.executable, str(tools / "prepare_system_update.py"),
        "--partition-csv", str(partition_csv),
        "--partition-table", str(table),
        "--application", str(build / flash["app"]["file"]),
        *resources,
        "--stage-dir", str(stage), "--release", release], check=True)
    output = build / f"{project_name}-system-update.irisfw"
    subprocess.run([
        sys.executable, str(builder), str(stage / "manifest.json"),
        "--component-root", str(stage), "--target-layout", str(table),
        "--output", str(output)], check=True)
    sys.path.insert(0, str(tools))
    from mosaico_cli.ideas_firmware import validate_firmware

    validate_firmware(output.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".irisfw.sha256").write_text(f"{digest}  {output.name}\n")
    print(output)


if __name__ == "__main__":
    main()
