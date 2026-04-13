from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import time
from typing import Iterable


def _ensure_local_pytools() -> None:
    pytools_root = Path(
        os.environ.get(
            "CODEX_PYTOOLS",
            Path.home() / "AppData" / "Local" / "codex_pytools",
        )
    )
    if pytools_root.exists():
        sys.path.insert(0, str(pytools_root))


_ensure_local_pytools()

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return slug or "step"


def _build_driver(window_size: str, headless: bool) -> webdriver.Edge:
    options = Options()
    width, height = window_size.split(",", maxsplit=1)
    options.add_argument(f"--window-size={width},{height}")
    if headless:
        options.add_argument("--headless=new")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Edge(options=options)


def _wait_for_text(driver: webdriver.Edge, wait: WebDriverWait, text: str):
    xpath = f"//*[contains(normalize-space(),\"{text}\")]"
    return wait.until(EC.presence_of_element_located((By.XPATH, xpath)))


def _click_button(driver: webdriver.Edge, wait: WebDriverWait, text: str) -> None:
    xpath = f"//button[contains(normalize-space(),\"{text}\")]"
    wait.until(EC.element_to_be_clickable((By.XPATH, xpath))).click()


def _save_screenshot(driver: webdriver.Edge, output_dir: Path, index: int, name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{index:02d}-{_slugify(name)}.png"
    driver.save_screenshot(str(path))
    return path


def _iter_steps(raw_steps: Iterable[str]) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    for raw in raw_steps:
        if "=" not in raw:
            raise ValueError(f"无效 step: {raw}，格式必须是 verb=value")
        verb, value = raw.split("=", maxsplit=1)
        verb = verb.strip().lower()
        value = value.strip()
        if verb not in {"expect", "click", "shot", "wait"}:
            raise ValueError(f"不支持的 step 动作: {verb}")
        steps.append((verb, value))
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="在本机 Edge 中执行可复用的 GUI 浏览器检查。")
    parser.add_argument("--url", required=True, help="要打开的页面地址。")
    parser.add_argument(
        "--step",
        action="append",
        default=[],
        help="执行步骤，格式如 expect=资产管理报表控制台 / click=打开 主报表工作台 / wait=3 / shot=home。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "playwright"),
        help="截图输出目录。",
    )
    parser.add_argument(
        "--window-size",
        default="1600,1000",
        help="浏览器窗口大小，格式为 width,height。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="单步等待超时时间（秒）。",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="以 headless 模式运行。",
    )
    args = parser.parse_args()

    steps = _iter_steps(args.step)
    output_dir = Path(args.output_dir)
    driver = _build_driver(args.window_size, args.headless)
    wait = WebDriverWait(driver, args.timeout)

    try:
        driver.get(args.url)
        print(f"[open] {args.url}")
        for index, (verb, value) in enumerate(steps, start=1):
            if verb == "expect":
                _wait_for_text(driver, wait, value)
                print(f"[expect] {value}")
            elif verb == "click":
                _click_button(driver, wait, value)
                print(f"[click] {value}")
            elif verb == "shot":
                path = _save_screenshot(driver, output_dir, index, value)
                print(f"[shot] {path}")
            elif verb == "wait":
                seconds = float(value)
                time.sleep(seconds)
                print(f"[wait] {seconds:.1f}s")

        logs = driver.get_log("browser")
        if logs:
            print("[browser-log]")
            for entry in logs:
                print(entry)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
