"""Five chapters, one auditable set of simulated factory investment metrics."""
from pathlib import Path
from math import ceil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dashboard.data import DB, load_snapshot, select, version
from dashboard.style import BANNER, CSS, COLORS, PALETTE, RED
from src.generate_data import load_assumptions, load_config
from src.metrics import rates, quality_cost, monthly_volume, investment, divide

PAGES = ["1 · ปัญหาปัจจุบัน", "2 · จุดที่ควรแก้ก่อน", "3 · เงื่อนไขการพลาด", "4 · ผลเมื่อมี 3Eyes", "5 · การตัดสินใจลงทุน"]
DISCLAIMER = "ข้อมูลจำลองเพื่อการศึกษา · เปรียบเทียบต่างช่วงเวลา ไม่ใช่หลักฐานเหตุและผลของอุปกรณ์จริง"


def fmt(value, spec=",.0f"):
    return "คำนวณไม่ได้" if value is None or pd.isna(value) else format(value, spec)


def plot(fig):
    fig.update_layout(template="plotly_white", colorway=PALETTE,
                      font=dict(family="Tahoma, sans-serif", size=13, color="#52657c"),
                      margin=dict(l=20, r=20, t=55, b=30), height=380,
                      legend_title_text="", legend=dict(orientation="h", y=1.12, x=0),
                      paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", hoverlabel=dict(bgcolor="#172a46", font_color="white"))
    fig.update_xaxes(showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#edf1f7", zeroline=False, automargin=True)
    fig.update_traces(line=dict(width=3), marker=dict(size=7), selector=dict(type="scatter"))
    # Keep the explicit palette instead of letting Streamlit replace chart colors.
    st.plotly_chart(fig, use_container_width=True, theme=None)


def metric(column, label, value, numerator, denominator, spec=".1%"):
    column.metric(label, fmt(value, spec))
    column.caption(f"{numerator:,} / {denominator:,} ตัว")


def no_data(df):
    if df.empty:
        st.info("ไม่มีข้อมูลตามตัวกรองปัจจุบัน — เลือกลูกค้า ไลน์ กะ และช่วงวันที่ที่มีข้อมูล")
        return True
    return False


def comparison_missing(manual, assisted):
    if manual.empty or assisted.empty:
        st.warning("ข้อมูลไม่พอเปรียบเทียบ: ต้องมีทั้ง baseline และ assisted จึงคำนวณผลต่างและ ROI ได้")
        return True
    return False


def page1(manual, claims, params):
    st.title(PAGES[0])
    st.write("โรงงานมีของเสียผ่าน QC เท่าไร และลูกค้าเคลมกลับมาเท่าไร?")
    if no_data(manual):
        return
    k = rates(manual)
    cost = quality_cost(manual, claims, params["labor_cost_per_hour"])
    a, b, c, d = st.columns(4)
    metric(a, "Escape PPM", k["ppm"], k["escaped"], k["passed"], ",.0f")
    b.metric("ของเสียที่ผ่าน QC", f"{k['escaped']:,} ตัว")
    c.metric("จำนวนคืนจากเคลม", f"{cost['returned']:,} ตัว")
    d.metric("ต้นทุนคุณภาพในแบบจำลอง", f"฿{cost['total']:,.0f}")
    st.caption(f"ตรวจทั้งหมด {k['units']:,} ตัว · เคลม ฿{cost['claim']:,.0f} + แก้ไขงานคืน ฿{cost['rework']:,.0f} + มูลค่าเวลา QC ฿{cost['labor']:,.0f}")
    st.info(f"ข้อมูลช่วงนี้พบของเสียผ่าน QC {k['escaped']:,} ตัว แต่คืนจากเคลม {cost['returned']:,} ตัว — เป็นคนละจำนวน")
    weekly = []
    for week, group in manual.groupby(pd.to_datetime(manual.full_date).dt.to_period("W").astype(str)):
        r = rates(group)
        weekly.append({"สัปดาห์": week, "Escape PPM": r["ppm"], "ผ่าน QC": r["passed"], "หลุด": r["escaped"],
                       "ต้นทุน (บาท)": quality_cost(group, claims, params["labor_cost_per_hour"])["total"]})
    weekly = pd.DataFrame(weekly)
    left, right = st.columns(2)
    with left:
        st.subheader("แนวโน้มของเสียที่ผ่าน QC")
        plot(px.line(weekly, x="สัปดาห์", y="Escape PPM", markers=True, hover_data=["ผ่าน QC", "หลุด"], color_discrete_sequence=[RED]))
    with right:
        st.subheader("ต้นทุนคุณภาพรายสัปดาห์")
        plot(px.bar(weekly, x="สัปดาห์", y="ต้นทุน (บาท)", color_discrete_sequence=[COLORS["Manual"]]))
    st.success("การตัดสินใจ: เริ่มตรวจ lot และตำหนิที่มีของเสียผ่าน QC มาก ก่อนพิจารณาการลงทุน")


def page2(manual):
    st.title(PAGES[1])
    st.write("ตำหนิและ lot ใดเป็นแหล่งของเสียที่ผ่าน QC มากที่สุด?")
    if no_data(manual):
        return
    escaped = manual[manual.true_defect_key.ne(0) & manual.final_decision.eq("PASS")]
    counts = escaped.defect_name.value_counts().rename_axis("ตำหนิ").reset_index(name="หลุด")
    if counts.empty:
        st.info("ไม่พบของเสียที่ผ่าน QC ในข้อมูลที่เลือก; สัดส่วน Pareto คำนวณไม่ได้")
    else:
        counts["สะสม %"] = counts["หลุด"].cumsum() / len(escaped) * 100
        top = int(counts.head(3)["หลุด"].sum())
        st.info(f"ตำหนิ 3 อันดับแรกมีของเสียผ่าน QC {top:,}/{len(escaped):,} ตัว ({top/len(escaped):.1%})")
        fig = go.Figure()
        fig.add_bar(x=counts["ตำหนิ"], y=counts["หลุด"], name="ของเสียผ่าน QC", marker_color=PALETTE[:len(counts)],
                    text=counts["หลุด"], textposition="outside")
        fig.add_scatter(x=counts["ตำหนิ"], y=counts["สะสม %"], name="สะสม %", yaxis="y2", line_color=RED, mode="lines+markers")
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 100], ticksuffix="%"))
        plot(fig)
    line_rows = []
    for line, group in manual.groupby("production_line"):
        k = rates(group)
        line_rows.append({"ไลน์": line, "อัตราตำหนิ": k["defect_rate"], "ของเสียจริง": k["defects"], "ตรวจ": k["units"]})
    lines = pd.DataFrame(line_rows)
    fig = px.bar(lines, x="ไลน์", y="อัตราตำหนิ", color="ไลน์", hover_data=["ของเสียจริง", "ตรวจ"], color_discrete_sequence=PALETTE)
    fig.update_layout(showlegend=False)
    fig.update_yaxes(tickformat=".1%")
    plot(fig)
    st.dataframe(lines, hide_index=True, use_container_width=True)
    lots = manual.assign(escaped=manual.true_defect_key.ne(0) & manual.final_decision.eq("PASS"))
    lots = lots.groupby(["lot_code", "customer_name", "production_line"]).agg(
        ตรวจ=("unit_id", "size"), ของเสียจริง=("is_defect", "sum"), หลุด=("escaped", "sum")).reset_index()
    lots["อัตราตำหนิ"] = lots["ของเสียจริง"] / lots["ตรวจ"]
    st.subheader("Lot ที่ควรตรวจสอบก่อน")
    st.dataframe(lots.sort_values(["หลุด", "อัตราตำหนิ"], ascending=False).head(10), hide_index=True, use_container_width=True)
    st.success("การตัดสินใจ: ตรวจสอบกระบวนการของ lot ที่หลุดมาก และเทียบอัตราตำหนิพร้อมจำนวนตัวอย่างของแต่ละไลน์")


def page3(manual):
    st.title(PAGES[2])
    st.write("เงื่อนไขใดสัมพันธ์กับการพลาดในข้อมูลจำลอง?")
    if no_data(manual):
        return
    bad = manual[manual.true_defect_key.ne(0)].copy()
    if bad.empty:
        st.info("ไม่มีของเสียจริงในข้อมูลที่เลือก — Human Miss Rate คำนวณไม่ได้ (ตัวหาร 0)")
        return
    bad["miss"] = bad.final_decision.eq("PASS").astype(int)
    late = bad[bad.hour_in_shift.between(7, 8)]
    st.info(f"ชั่วโมง 7–8 พลาด {int(late['miss'].sum()):,}/{len(late):,} ตัว: {fmt(divide(late['miss'].sum(), len(late)), '.1%')}")
    st.caption("แนวโน้มชั่วโมง กะ ประสบการณ์ และแสงเกิดจากสมมติฐานที่ใส่ใน generator ไม่ใช่ข้อสรุปเกี่ยวกับพนักงานจริง")
    for fields, title in [(["hour_in_shift", "shift_name"], "ชั่วโมงและกะ"),
                           (["experience_band"], "ประสบการณ์"), (["lighting_cond"], "สภาพแสง")]:
        grouped = bad.groupby(fields).agg(พลาด=("miss", "sum"), ของเสียจริง=("miss", "size")).reset_index()
        grouped["Human Miss Rate"] = grouped["พลาด"] / grouped["ของเสียจริง"]
        if len(fields) == 2:
            fig = px.line(grouped, x=fields[0], y="Human Miss Rate", color=fields[1], markers=True,
                          hover_data=["พลาด", "ของเสียจริง"], title=title, color_discrete_sequence=PALETTE)
        else:
            fig = px.bar(grouped, x=fields[0], y="Human Miss Rate", color=fields[0], hover_data=["พลาด", "ของเสียจริง"], title=title,
                         color_discrete_sequence=PALETTE)
            fig.update_layout(showlegend=False)
        fig.update_yaxes(tickformat=".0%")
        plot(fig)
        with st.expander(f"จำนวนตัวอย่าง: {title}"):
            st.dataframe(grouped, hide_index=True, use_container_width=True)
    st.success("การตัดสินใจ: เก็บข้อมูลจริงแยกชั่วโมงและแสง เพื่อทดสอบสมมติฐานก่อนปรับตารางงานหรือสภาพแวดล้อม")


def page4(manual, assisted, scenario_name):
    st.title(PAGES[3])
    st.write(f"{scenario_name}: ลดความเสี่ยงได้เท่าไร แลกกับภาระตรวจยืนยันเท่าไร?")
    if comparison_missing(manual, assisted):
        return
    km, ka = rates(manual), rates(assisted)
    st.info(f"Escape PPM: Manual {fmt(km['ppm'])} → 3Eyes {fmt(ka['ppm'])}; ตัวหารคือจำนวน final PASS ของแต่ละช่วง")
    cols = st.columns(4)
    for offset, name, k in [(0, "Manual", km), (2, "3Eyes", ka)]:
        metric(cols[offset], f"PPM · {name}", k["ppm"], k["escaped"], k["passed"], ",.0f")
        metric(cols[offset+1], f"Final Recall · {name}", k["recall"], k["caught"], k["defects"])
    recall_rows = []
    for label, frame in [("Manual", manual), ("3Eyes", assisted)]:
        for defect, group in frame[frame.true_defect_key.ne(0)].groupby("defect_name"):
            k = rates(group)
            recall_rows.append({"ตำหนิ": defect, "ระบบ": label, "Recall": k["recall"], "จับได้": k["caught"], "ของเสียจริง": k["defects"]})
    if recall_rows:
        recalls = pd.DataFrame(recall_rows)
        fig = px.bar(recalls, x="ตำหนิ", y="Recall", color="ระบบ", barmode="group", color_discrete_map=COLORS, hover_data=["จับได้", "ของเสียจริง"])
        fig.update_yaxes(tickformat=".0%")
        plot(fig)
        st.dataframe(recalls, hide_index=True, use_container_width=True)
    else:
        st.info("Recall แยกตำหนิคำนวณไม่ได้: ไม่มีของเสียจริง")
    cols = st.columns(4)
    metric(cols[0], "Device False Alarm", ka["false_alarm"], ka["device_false_alarms"], ka["assisted_good"])
    metric(cols[1], "Final False Reject", ka["false_reject"], ka["final_false_rejects"], ka["good"])
    metric(cols[2], "Uncertain Rate", ka["uncertain"], ka["uncertain_count"], ka["assisted"])
    metric(cols[3], "Override Rate", ka["override"], ka["overrides"], ka["device_fail"])
    st.caption("Override คือเครื่อง FAIL แต่คนเปลี่ยนเป็น PASS ไม่ใช่มาตรวัดความเชื่อใจโดยตรง; Device False Alarm และ Final False Reject เป็นคนละขั้น")
    timing = pd.DataFrame([{"ระบบ": name, "ตัวอย่าง": k["units"], "วินาที/ตัว": k["avg_seconds"],
                            "กำลังตรวจเชิงทฤษฎี (ตัว/ชั่วโมง)": k["throughput"],
                            "Final False Reject": fmt(k["false_reject"], ".1%"),
                            "งานดีคัดทิ้ง / งานดี": f"{k['final_false_rejects']} / {k['good']}"}
                           for name, k in [("Manual", km), ("3Eyes", ka)]])
    st.dataframe(timing, hide_index=True, use_container_width=True)
    st.success("การตัดสินใจ: เลือกทดลองสถานการณ์ที่ลดของเสียได้ พร้อมประเมินเวลาตรวจยืนยันและงานดีที่ถูกคัดทิ้ง")


def page5(manual, assisted_by_scenario, claims, params, interval, selected):
    st.title(PAGES[4])
    st.write("อุปกรณ์อาจลดของเสีย แต่คุ้มทุนภายใต้ปริมาณงานและต้นทุนแบบใด?")
    if comparison_missing(manual, assisted_by_scenario[selected]):
        return
    default = monthly_volume(len(manual), *interval)
    volume = st.number_input("ปริมาณตรวจต่อเดือน (ตัว)", min_value=0.0, value=round(default, 2), step=1000.0,
                             key=f"volume_{interval[0]}_{interval[1]}_{len(manual)}")
    days = (pd.Timestamp(interval[1])-pd.Timestamp(interval[0])).days+1
    st.caption(f"ค่าเริ่มต้น = baseline {len(manual):,} ตัว ÷ {days} วัน × 30.4375 วัน/เดือน = {default:,.2f} ตัว/เดือน")
    capital = params["device_unit_price"] * params["device_count"]
    subscription = params["device_subscription_per_month"] * params["device_count"]
    mc = quality_cost(manual, claims, params["labor_cost_per_hour"])
    rows, projections, result_by_name = [], [], {}
    for name, frame in assisted_by_scenario.items():
        ac = quality_cost(frame, claims, params["labor_cost_per_hour"])
        result = investment(mc["per_unit"], ac["per_unit"] if ac else None, volume, subscription, capital)
        if result is None:
            rows.append({"สถานการณ์": name, "สถานะ": "ข้อมูลไม่พอเปรียบเทียบ"})
            continue
        result_by_name[name] = result
        k = rates(frame)
        rows.append({"สถานการณ์": name, "ตัวอย่าง manual": len(manual), "ตัวอย่าง assisted": len(frame),
                     "ต้นทุน manual/ตัว": mc["per_unit"], "ต้นทุน assisted/ตัว": ac["per_unit"],
                     "ประหยัดต่อเดือน": result["monthly_saving"], "สุทธิ 6 เดือน": result["net_6m"],
                     "ROI 6 เดือน": fmt(result["roi_6m"], ".1%"), "คืนทุน (เดือน)": "ไม่คืนทุน" if result["payback"] is None else fmt(result["payback"], ".1f"),
                     "ขั้นต่ำครอบคลุมค่าบริการ (ตัว/เดือน)": fmt(ceil(result["minimum_volume"]) if result["minimum_volume"] is not None else None),
                     "Escape PPM": fmt(k["ppm"]), "หลุด / ผ่าน QC": f"{k['escaped']} / {k['passed']}",
                     "สถานะ": "ไม่คืนทุนภายใต้สมมติฐานนี้" if result["payback"] is None else "คืนทุนได้ตามแบบจำลอง"})
        projections.append(result["projection"].assign(scenario=name))
    table = pd.DataFrame(rows)
    chosen = result_by_name[selected]
    st.info(f"{selected}: ประหยัดสุทธิต่อเดือน ฿{chosen['monthly_saving']:,.2f} · " +
            ("ไม่คืนทุนภายใต้สมมติฐานนี้" if chosen["payback"] is None else f"คืนทุน {chosen['payback']:,.1f} เดือน"))
    cols = st.columns(3)
    cols[0].metric("ROI ที่ 6 เดือน", fmt(chosen["roi_6m"], ".1%"))
    cols[1].metric("ระยะคืนทุน (เดือน)", "ไม่คืนทุน" if chosen["payback"] is None else fmt(chosen["payback"], ".1f"))
    minimum_units = ceil(chosen["minimum_volume"]) if chosen["minimum_volume"] is not None else None
    cols[2].metric("ขั้นต่ำครอบคลุมค่าบริการ", fmt(minimum_units) + " ตัว/เดือน")
    summary = table[["สถานการณ์", "ประหยัดต่อเดือน", "สุทธิ 6 เดือน", "ROI 6 เดือน", "คืนทุน (เดือน)"]]
    st.dataframe(summary, hide_index=True, use_container_width=True,
                 column_config={"ประหยัดต่อเดือน": st.column_config.NumberColumn(format="%.2f"),
                                "สุทธิ 6 เดือน": st.column_config.NumberColumn(format="%.2f")})
    st.caption(f"ตัวอย่าง baseline {len(manual):,} ตัว; assisted {selected} {len(assisted_by_scenario[selected]):,} ตัว — สามสถานการณ์เป็นน็อตชุดเดียวกัน")
    with st.expander("รายละเอียดต้นทุน จำนวนตัวอย่าง และจุดคุ้มทุนแต่ละสถานการณ์"):
        st.dataframe(table, hide_index=True, use_container_width=True)
    projection = pd.concat(projections, ignore_index=True)
    chosen_projection = projection[projection.scenario.eq(selected)]
    chart = chosen_projection.melt(id_vars=["month", "scenario"], value_vars=["Manual", "3Eyes"], var_name="ระบบ", value_name="ต้นทุนสะสม (บาท)")
    plot(px.line(chart, x="month", y="ต้นทุนสะสม (บาท)", color="ระบบ", color_discrete_map=COLORS, markers=True,
                 labels={"month": "เดือน"}))
    st.caption(f"ลงทุน ฿{capital:,.0f} · ค่าบริการ ฿{subscription:,.0f}/เดือน · ต้นทุน manual ฿{mc['per_unit']:.4f}/ตัว")
    st.code("ประหยัดต่อเดือน = (ต้นทุน manual/ตัว − ต้นทุน assisted/ตัว) × ปริมาณต่อเดือน − ค่าบริการ\nROI 6 เดือน = (ประหยัดต่อเดือน × 6 − เงินลงทุน) ÷ เงินลงทุน")
    st.caption("ปริมาณขั้นต่ำปัดขึ้นเป็นจำนวนเต็ม ครอบคลุมเฉพาะค่าบริการ ไม่รวมคืนเงินลงทุน; มูลค่าเวลาที่ลดลงเป็นผลประโยชน์เทียบเท่าค่าแรง ไม่ใช่เงินสดที่ประหยัดจริงทั้งหมด")
    st.download_button("ดาวน์โหลดตาราง ROI (CSV)", table.to_csv(index=False).encode("utf-8-sig"), "roi.csv", "text/csv")
    st.success("การตัดสินใจ: ใช้ปริมาณงานและต้นทุนจริงของโรงงานทดสอบจุดคุ้มทุน และยืนยันคุณภาพด้วยการทดลองก่อนลงทุน")


def main():
    st.set_page_config(page_title="3Eyes | Factory Decision", page_icon="◉", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(BANNER, unsafe_allow_html=True)
    st.warning(DISCLAIMER)
    if not DB.exists():
        st.error("ไม่พบ SQLite snapshot — ผู้ดูแลต้องรัน python run.py all ก่อนเผยแพร่")
        return
    facts, claims, dates, scenarios, runs = load_snapshot(str(DB), version(DB))
    params = load_assumptions()
    with st.sidebar:
        st.title("3Eyes")
        st.caption("จากคุณภาพสินค้า สู่การตัดสินใจลงทุน")
        page = st.radio("ตอนของเรื่อง", PAGES)
        intervals = {}
        for key, phase, label in [("baseline", "baseline_manual", "ช่วง baseline"), ("assisted", "assisted_3eyes", "ช่วง assisted")]:
            available = pd.to_datetime(dates.loc[dates.period_phase.eq(phase), "full_date"])
            intervals[key] = st.date_input(label, value=(available.min().date(), available.max().date()),
                                          min_value=available.min().date(), max_value=available.max().date(), key=key)
        selections = []
        for col, label in [("customer_name", "ลูกค้า"), ("production_line", "ไลน์"), ("shift_name", "กะ")]:
            options = sorted(facts[col].unique())
            selections.append(st.multiselect(label, options, default=options, key=col))
        selected = st.selectbox("สถานการณ์ assisted", scenarios.scenario_name.tolist(), index=1)
        st.caption("เลือกว่าง = ไม่มีข้อมูล; หน้า 1–3 ใช้ baseline เท่านั้น")
    manual = select(facts, "manual", 0, intervals["baseline"], *selections)
    assisted = {s.scenario_name: select(facts, "assisted", s.scenario_key, intervals["assisted"], *selections)
                for s in scenarios.itertuples()}
    st.caption(f"Baseline: {' → '.join(map(str, intervals['baseline']))} · Assisted: {' → '.join(map(str, intervals['assisted']))}")
    if page == PAGES[0]:
        page1(manual, claims, params)
    elif page == PAGES[1]:
        page2(manual)
    elif page == PAGES[2]:
        page3(manual)
    elif page == PAGES[3]:
        page4(manual, assisted[selected], selected)
    else:
        page5(manual, assisted, claims, params, intervals["baseline"], selected)
    with st.expander("ที่มาของข้อมูลและคุณภาพข้อมูล"):
        st.write(f"Grain: น็อตหนึ่งตัวต่อ mode/scenario · Seed {load_config()['seed']} · 7 ประเภทตำหนิ + งานดี 1 กลุ่ม")
        st.write(f"แถวตรวจ {len(facts):,} · น็อตจำลองไม่ซ้ำ {facts.unit_id.nunique():,} ตัว · แถวเคลม {len(claims):,}")
        st.caption(f"Snapshot SHA-256: {version(DB)}")
        validation = runs[runs.step_name.eq("validate")]
        st.write("ETL validation: " + (validation.iloc[0].status if not validation.empty else "ไม่มีผลตรวจ"))
        st.dataframe(runs.head(5), hide_index=True, use_container_width=True)
        st.dataframe(pd.read_csv(ROOT / "config/assumptions.csv"), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(load_config()["scenarios"]), hide_index=True, use_container_width=True)
        st.caption("แต่ละ lot อยู่วันและกะเดียว; หนึ่งตำหนิหลักต่อน็อต; เคลมลงวันเดียวกับ lot; ผลเครื่องจำลองด้วยความน่าจะเป็น ไม่มี anomaly score")
        st.caption("ขอบเขตต้นทุนไม่รวมมูลค่างานดีคัดทิ้ง ค่าซ่อมเครื่อง ดอกเบี้ย และภาษี; กำลังตรวจเป็นเชิงทฤษฎี ไม่รวมเวลาหยุดพัก")
    st.caption(DISCLAIMER)


if __name__ == "__main__":
    main()
