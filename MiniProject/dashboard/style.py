"""Shared visual styling for the factory dashboard."""

PALETTE = ["#0d9488", "#6366f1", "#f59e0b", "#e85d75", "#0284c7", "#a855f7", "#84a329"]
COLORS = {"Manual": "#6366f1", "3Eyes": "#0d9488"}
RED = "#e85d75"

CSS = """
<style>
.stApp {background: #f3f6fb;}
.block-container {padding-top: 3.5rem; padding-bottom: 2rem; max-width: 1500px;}
h1, h2, h3 {color: #172a46; letter-spacing: -.025em;}
h1 {font-size: 2.1rem !important;}
[data-testid="stSidebar"] {background: #e9eff8; border-right: 1px solid #d9e2ef;}
[data-testid="stSidebar"] h1 {color: #0f766e;}
[data-testid="stSidebar"] [role="radiogroup"] {gap: .45rem;}
[data-testid="stSidebar"] [role="radiogroup"] label {
    background: #fff; border: 1px solid #d9e2ef; border-radius: 10px; padding: .6rem .7rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: #d6f3ed; border-color: #0d9488;
}
.brand-banner {
    background: linear-gradient(115deg, #172a46 0%, #21435c 65%, #0f766e 100%);
    border-radius: 18px; padding: 1.4rem 1.7rem; color: white; margin-bottom: 1rem;
    box-shadow: 0 8px 24px #172a4612;
}
.brand-eyebrow {color: #72e1cd; font-size: .75rem; letter-spacing: .18em; font-weight: 700;}
.brand-title {font-size: 1.6rem; font-weight: 700; margin: .25rem 0;}
.brand-subtitle {color: #d5e6f2; font-size: .9rem;}
[data-testid="stMetric"] {
    background: white; border: 1px solid #dfe7f1; border-top: 4px solid #0d9488;
    border-radius: 12px; padding: 1rem 1.1rem; min-height: 126px;
    box-shadow: 0 4px 16px #172a4608;
}
[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {border-top-color: #6366f1;}
[data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {border-top-color: #f59e0b;}
[data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {border-top-color: #e85d75;}
[data-testid="stMetricValue"] {font-size: 1.7rem; color: #172a46;}
[data-testid="stMetricLabel"] {color: #52657c;}
[data-testid="stPlotlyChart"] {
    background: white; border: 1px solid #dfe7f1; border-radius: 14px;
    padding: .35rem; box-shadow: 0 4px 16px #172a4608;
}
[data-testid="stExpander"] {background: white; border-radius: 12px;}
[data-testid="stAlert"] {border-radius: 10px;}
[data-testid="stDownloadButton"] button {border-color: #0d9488; color: #0f766e; border-radius: 9px;}
@media (max-width: 768px) {
    .block-container {padding-left: 1rem; padding-right: 1rem;}
    .brand-banner {padding: 1rem;}
    h1 {font-size: 1.65rem !important;}
}
</style>
"""

BANNER = """
<div class="brand-banner">
  <div class="brand-eyebrow">3EYES / FACTORY DECISION LAB</div>
  <div class="brand-title">มองเห็นคุณภาพ ตัดสินใจด้วยข้อมูล</div>
  <div class="brand-subtitle">สำรวจความเสี่ยงในโรงงาน เปรียบเทียบผลการตรวจ และประเมินความคุ้มค่าการลงทุน</div>
</div>
"""
