from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import streamlit as st

from src.asset_mgnt_report.config.defaults import build_app_config


config = build_app_config()

st.set_page_config(page_title="Asset Management Report", page_icon="📊", layout="wide")
st.title("资产管理报表控制台")
st.caption("统一参数配置、执行报表、触发验证。")

with st.sidebar:
    st.header("运行参数")
    debug = st.checkbox("启用 debug", value=config.debug)
    use_proxy = st.checkbox("启用代理", value=config.use_proxy)
    selected = st.multiselect(
        "主报表模块",
        ["cpi", "gdp", "interest_rate", "carry_trade", "stock_index", "currency", "precious_metals", "bonds", "crypto"],
        default=["cpi", "gdp", "interest_rate", "carry_trade", "stock_index", "currency", "precious_metals", "bonds", "crypto"],
    )

def _run_script(script_name: str) -> tuple[int, str]:
    env = dict(**subprocess.os.environ)
    env["AMR_DEBUG"] = "true" if debug else "false"
    env["AMR_USE_PROXY"] = "true" if use_proxy else "false"
    process = subprocess.run(
        [sys.executable, script_name],
        cwd=str(config.project_root),
        capture_output=True,
        text=True,
        env=env,
    )
    return process.returncode, (process.stdout + "\n" + process.stderr).strip()


col1, col2, col3, col4 = st.columns(4)
if col1.button("运行主报表", use_container_width=True):
    logs: list[str] = []
    for module_name in selected:
        script_map = {
            "cpi": "cpi.py",
            "gdp": "GDP_new.py",
            "interest_rate": "interest_rate.py",
            "carry_trade": "carry_trade.py",
            "stock_index": "asset_stock_index.py",
            "currency": "currency.py",
            "precious_metals": "precious_metals.py",
            "bonds": "bonds.py",
            "crypto": "crypto_market_report.py",
        }
        code, output = _run_script(script_map[module_name])
        logs.append(f"## {module_name} ({code})\n\n```text\n{output}\n```")
    st.markdown("\n\n".join(logs))

if col2.button("运行 Gainer", use_container_width=True):
    code, output = _run_script("Gainer.py")
    st.code(output, language="text")
    st.write(f"exit code: {code}")

if col3.button("运行整体表", use_container_width=True):
    code, output = _run_script("整体.py")
    st.code(output, language="text")
    st.write(f"exit code: {code}")

if col4.button("运行全量校验", use_container_width=True):
    code, output = _run_script("tools_validate.py")
    st.code(output, language="text")
    st.write(f"exit code: {code}")

st.subheader("目录")
st.write(f"项目根目录: `{config.project_root}`")
st.write(f"种子数据目录: `{config.seed_data_dir}`")
st.write(f"本地数据目录: `{config.local_data_dir}`")
st.write(f"输出目录: `{config.output_dir}`")
