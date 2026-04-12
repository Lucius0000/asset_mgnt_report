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

def _run_script(module_name: str) -> tuple[int, str]:
    env = dict(**subprocess.os.environ)
    env["AMR_DEBUG"] = "true" if debug else "false"
    env["AMR_USE_PROXY"] = "true" if use_proxy else "false"
    process = subprocess.run(
        [sys.executable, "-m", module_name],
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
            "cpi": "scripts.pipelines.cpi_report",
            "gdp": "scripts.pipelines.gdp_report",
            "interest_rate": "scripts.pipelines.interest_rate_report",
            "carry_trade": "scripts.pipelines.carry_trade_report",
            "stock_index": "scripts.pipelines.stock_index_report",
            "currency": "scripts.pipelines.fx_report",
            "precious_metals": "scripts.pipelines.precious_metals_report",
            "bonds": "scripts.pipelines.bond_report",
            "crypto": "scripts.pipelines.crypto_report",
        }
        code, output = _run_script(script_map[module_name])
        logs.append(f"## {module_name} ({code})\n\n```text\n{output}\n```")
    st.markdown("\n\n".join(logs))

if col2.button("运行 Gainer", use_container_width=True):
    code, output = _run_script("scripts.entrypoints.run_gainer")
    st.code(output, language="text")
    st.write(f"exit code: {code}")

if col3.button("运行整体表", use_container_width=True):
    code, output = _run_script("scripts.entrypoints.run_overall")
    st.code(output, language="text")
    st.write(f"exit code: {code}")

if col4.button("运行全量校验", use_container_width=True):
    code, output = _run_script("scripts.validation.validate_outputs")
    st.code(output, language="text")
    st.write(f"exit code: {code}")

st.subheader("目录")
st.write(f"项目根目录: `{config.project_root}`")
st.write(f"种子数据目录: `{config.seed_data_dir}`")
st.write(f"本地数据目录: `{config.local_data_dir}`")
st.write(f"输出目录: `{config.output_dir}`")
