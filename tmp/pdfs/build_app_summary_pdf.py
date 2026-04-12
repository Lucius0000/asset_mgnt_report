from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, KeepTogether, ListFlowable, ListItem, PageTemplate, Paragraph, Spacer


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_PDF = OUTPUT_DIR / "asset_mgnt_report_app_summary_cn.pdf"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_NAME = "MicrosoftYaHei"


def register_font() -> None:
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCN", parent=styles["Title"], fontName=FONT_NAME, fontSize=18, leading=22, textColor=colors.HexColor("#16324F"), spaceAfter=4))
    styles.add(ParagraphStyle(name="SubTitleCN", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9.2, leading=12, textColor=colors.HexColor("#4A5A6A"), spaceAfter=8))
    styles.add(ParagraphStyle(name="SectionCN", parent=styles["Heading2"], fontName=FONT_NAME, fontSize=10.5, leading=13, textColor=colors.white, backColor=colors.HexColor("#1F5A7A"), borderPadding=(4, 6, 4, 6), spaceAfter=5))
    styles.add(ParagraphStyle(name="BodyCN", parent=styles["BodyText"], fontName=FONT_NAME, fontSize=8.7, leading=11.2, alignment=TA_LEFT, textColor=colors.HexColor("#1E2933"), spaceAfter=3))
    styles.add(ParagraphStyle(name="SmallCN", parent=styles["BodyText"], fontName=FONT_NAME, fontSize=8.2, leading=10.3, textColor=colors.HexColor("#334155"), spaceAfter=2))
    return styles


def bullet_list(items, style, left_indent=10):
    return ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=0) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=left_indent,
        bulletFontName=FONT_NAME,
        bulletFontSize=7,
        spaceAfter=3,
    )


def section(title, body_flowables):
    return KeepTogether([Paragraph(title, STYLES["SectionCN"]), *body_flowables, Spacer(1, 3)])


def build_story():
    left = [
        Paragraph("asset_mgnt_report 应用摘要", STYLES["TitleCN"]),
        Paragraph("基于仓库内 Readme.md、main.py、Gainer.py、requirements.txt 与 stock_us_cn_hk/README.md 整理", STYLES["SubTitleCN"]),
        section("它是什么", [
            Paragraph("这是一个以 Python 脚本驱动的资产管理/双周报生成工具，用于抓取宏观与市场数据并输出 Excel/图片报表。", STYLES["BodyCN"]),
            Paragraph("仓库主入口会批量运行 CPI、GDP、利率、汇率、股票市值、债券、商品贵金属与加密货币模块；Web 界面或长期运行服务 <b>Not found in repo</b>。", STYLES["BodyCN"]),
        ]),
        section("它面向谁", [
            Paragraph("主要面向需要定期产出资产配置/市场周报的投研、资产管理或数据分析人员。", STYLES["BodyCN"]),
        ]),
        section("它做什么", [
            bullet_list([
                "批量获取 CPI、GDP、利率、利差、汇率、股票、债券、商品、加密货币数据。",
                "按模块生成 Excel 指标表，并输出部分趋势图到 output/。",
                "支持单独运行 Gainer.py，汇总股票、债券、黄金、BTC 的市值变化。",
                "支持单独运行 整体.py，计算整体表中的 Sharpe Ratio 与汇总表现。",
                "保留 output/raw_data/ 原始数据，便于 debug 与交叉验证。",
                "为 stock_us_cn_hk/ 子目录生成中港美二级市场分类周报。",
            ], STYLES["BodyCN"]),
        ]),
    ]

    right = [
        section("如何工作", [
            bullet_list([
                "入口层: main.py 依次调用 cpi.py、GDP_new.py、interest_rate.py、carry_trade.py、asset_stock_index.py、currency.py、bonds.py、crypto_market_report.py。",
                "数据源层: 依赖 akshare、yfinance、fredapi、pandas_datareader、pycoingecko；部分香港 CPI、恒生成分股、MSPD、沪深300名单需手工放入 data/。",
                "处理层: 各脚本用 pandas/numpy 计算同比、环比、年化收益、波动率、市值等指标。",
                "输出层: 结果写入 output/ 下的 xlsx/png；output/raw_data/ 存中间原始数据。",
                "补充流程: Gainer.py 聚合跨资产市值变化，整体.py 依赖人工整理的 data/整体.xlsx 再做总表计算。",
                "服务编排、数据库、消息队列、前后端分离架构 <b>Not found in repo</b>。",
            ], STYLES["SmallCN"]),
        ]),
        section("如何运行", [
            bullet_list([
                "安装依赖: pip install -r requirements.txt。",
                "准备手工数据: 将 README 指定的香港 CPI、恒生成分股、MSPD、沪深300名单放入 data/。",
                "设置环境变量: 某些 FRED 数据需要 FRED_API_KEY。",
                "生成主报表: python main.py。",
                "需要总表时再运行: python 整体.py；需要 Gainer 汇总时运行: python Gainer.py。",
            ], STYLES["BodyCN"]),
        ]),
        section("最小提醒", [
            Paragraph("README 明确说明部分流程仍含人工准备步骤，因此该项目更像“半自动化报表流水线”，不是开箱即用的单命令应用。", STYLES["BodyCN"]),
        ]),
    ]

    return left + [FrameBreak()] + right


def build_pdf():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUTPUT_PDF), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=11 * mm, bottomMargin=10 * mm)
    gap = 6 * mm
    frame_width = (doc.width - gap) / 2
    frames = [
        Frame(doc.leftMargin, doc.bottomMargin, frame_width, doc.height, id="left"),
        Frame(doc.leftMargin + frame_width + gap, doc.bottomMargin, frame_width, doc.height, id="right"),
    ]
    doc.addPageTemplates([PageTemplate(id="TwoCol", frames=frames)])
    doc.build(build_story())


if __name__ == "__main__":
    register_font()
    STYLES = build_styles()
    build_pdf()
    print(OUTPUT_PDF)
