from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/warehouse/threeeyes_dw.db"
DISCLAIMER = "ข้อมูลจำลองเพื่อการศึกษา — ค่าความสามารถของอุปกรณ์เป็นสมมติฐานเชิงสถานการณ์ ไม่ใช่ผลทดสอบจริง"
st.set_page_config(page_title="3Eyes | QC Narrative Dashboard", page_icon="👁️", layout="wide")

@st.cache_data
def query(sql, params=()):
    with sqlite3.connect(DB) as con:
        return pd.read_sql_query(sql, con, params=params)

def filters():
    dims = query("SELECT MIN(full_date) min_d,MAX(full_date) max_d FROM dim_date")
    customers = query("SELECT DISTINCT customer_name FROM dim_lot ORDER BY 1").customer_name.tolist()
    lines = query("SELECT DISTINCT production_line FROM dim_lot ORDER BY 1").production_line.tolist()
    scenarios = query("SELECT scenario_key,scenario_name FROM dim_scenario WHERE scenario_key>0 ORDER BY scenario_key")
    with st.sidebar:
        st.title("ตัวกรอง")
        dates = st.date_input("ช่วงวันที่", (pd.to_datetime(dims.min_d[0]).date(), pd.to_datetime(dims.max_d[0]).date()))
        customer = st.multiselect("ลูกค้า", customers, default=customers)
        line = st.multiselect("สายการผลิต", lines, default=lines)
        scenario_name = st.selectbox("สถานการณ์อุปกรณ์", scenarios.scenario_name.tolist(), index=1)
        shifts = st.multiselect("กะ", ["เช้า", "บ่าย", "ดึก"], default=["เช้า", "บ่าย", "ดึก"])
        st.info("ข้อมูลทุกชุดใน Dashboard เป็นข้อมูลจำลอง")
    scenario = int(scenarios.loc[scenarios.scenario_name == scenario_name, "scenario_key"].iloc[0])
    if not isinstance(dates, (tuple, list)) or len(dates) != 2:
        dates = (pd.to_datetime(dims.min_d[0]).date(), pd.to_datetime(dims.max_d[0]).date())
    return {"start": str(dates[0]), "end": str(dates[1]), "customers": customers if not customer else customer,
            "lines": lines if not line else line, "scenario": scenario, "scenario_name": scenario_name,
            "shifts": shifts or ["เช้า", "บ่าย", "ดึก"]}

def filtered(mode=None, scenario=None):
    f = st.session_state.filters
    marks, lmarks, smarks = ",".join("?" for _ in f["customers"]), ",".join("?" for _ in f["lines"]), ",".join("?" for _ in f["shifts"])
    scn = scenario if scenario is not None else (0 if mode == "manual" else f["scenario"])
    mode_sql, mode_args = (" AND f.inspection_mode=?", [mode]) if mode else ("", [])
    return query(f"""SELECT f.*,d.full_date,d.year,d.week_of_year,d.period_phase,s.shift_name,
      i.experience_band,l.customer_name,l.production_line,df.defect_name,df.is_defect
      FROM fact_inspection f JOIN dim_date d USING(date_key) JOIN dim_shift s USING(shift_key)
      JOIN dim_inspector i USING(inspector_key) JOIN dim_lot l USING(lot_key) JOIN dim_defect df ON df.defect_key=f.true_defect_key
      WHERE d.full_date BETWEEN ? AND ? AND l.customer_name IN ({marks}) AND l.production_line IN ({lmarks})
      AND s.shift_name IN ({smarks}) AND f.scenario_key=? {mode_sql}""",
      [f["start"], f["end"], *f["customers"], *f["lines"], *f["shifts"], scn, *mode_args])

def rates(df):
    defects = df[df.is_defect == 1]
    caught = int((defects.final_decision == "FAIL").sum()); escaped = len(defects) - caught
    good = df[df.is_defect == 0]; false = int((good.final_decision == "FAIL").sum())
    passed = int((df.final_decision == "PASS").sum())
    return {"units": len(df), "defects": len(defects), "caught": caught, "escaped": escaped,
        "ppm": escaped / passed * 1e6 if passed else 0, "recall": caught / len(defects) if len(defects) else 0,
        "false_alarm": false / len(good) if len(good) else 0,
        "uncertain": float((df.device_decision == "UNCERTAIN").mean()) if len(df) else 0,
        "overrides": int(df.override_flag.sum()), "device_fail": int((df.device_decision == "FAIL").sum()),
        "avg_seconds": float(df.inspect_seconds.mean()) if len(df) else 0}

def fmt_thb(v): return f"฿{v:,.0f}"
def claim_cost(df, scenario):
    keys=df.lot_key.drop_duplicates().astype(int).tolist()
    if not keys: return 0.0
    marks=",".join("?" for _ in keys)
    return float(query(f"SELECT COALESCE(SUM(claim_cost+rework_cost),0) cost FROM fact_customer_claim WHERE scenario_key=? AND lot_key IN ({marks})",[scenario,*keys]).cost[0])

def assumptions():
    return pd.read_csv(ROOT / "config/assumptions.csv").set_index("param").value.astype(float).to_dict()

def header(title, lead): st.title(title); st.subheader(lead)
def nothing(df):
    if df.empty: st.info("ไม่มีข้อมูลตามตัวกรองปัจจุบัน ลองขยายช่วงวันที่หรือล้างตัวกรองบางรายการ")
    return df.empty

def page1():
    header("1 · ปัญหา", "ของเสียจาก QC หลุดถึงลูกค้ากี่ชิ้น และสร้างต้นทุนเท่าไร")
    df = filtered("manual", 0)
    if nothing(df): return
    k = rates(df)
    params=assumptions(); claim=claim_cost(df,0)
    cost = claim + df.inspect_seconds.sum() * params["labor_cost_per_hour"] / 3600
    a,b,c = st.columns(3); a.metric("Escape PPM", f"{k['ppm']:,.0f}"); b.metric("ของเสียหลุด", f"{k['escaped']:,} ชิ้น"); c.metric("ต้นทุนคุณภาพโดยประมาณ", fmt_thb(cost))
    df["week"] = pd.to_datetime(df.full_date).dt.to_period("W").astype(str)
    params=assumptions()
    weekly_rows=[]
    for week, group in df.groupby("week"):
        weekly_rows.append({"week":week,"Escape PPM":rates(group)["ppm"],
            "Cost of quality":claim_cost(group,0)+group.inspect_seconds.sum()*params["labor_cost_per_hour"]/3600})
    weekly=pd.DataFrame(weekly_rows)
    st.plotly_chart(px.line(weekly,x="week",y="Escape PPM",markers=True,color_discrete_sequence=["#d94841"]),use_container_width=True)
    st.plotly_chart(px.line(weekly,x="week",y="Cost of quality",markers=True,color_discrete_sequence=["#2878a5"]),use_container_width=True)
    st.caption(f"ในช่วง manual พบของเสียหลุด {k['escaped']:,} ชิ้น คิดเป็น {k['ppm']:,.0f} PPM")

def page2():
    df = filtered("manual", 0)
    if nothing(df): return
    bad = df[df.is_defect == 1]
    counts = bad.defect_name.value_counts().rename_axis("ประเภทตำหนิ").reset_index(name="จำนวน")
    counts["สะสม %"] = counts.จำนวน.cumsum() / max(1, counts.จำนวน.sum()) * 100
    share=counts.head(3)["จำนวน"].sum()/max(1,len(bad))
    header("2 · ตำหนิอยู่ตรงไหน", f"ตำหนิ 3 ประเภทแรกคิดเป็น {share:.1%} ของตำหนิทั้งหมด")
    fig = go.Figure(); fig.add_bar(x=counts["ประเภทตำหนิ"], y=counts.จำนวน, name="จำนวนตำหนิ", marker_color="#d94841")
    fig.add_scatter(x=counts["ประเภทตำหนิ"], y=counts["สะสม %"], name="สะสม %", yaxis="y2", mode="lines+markers")
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0,100], ticksuffix="%"))
    st.plotly_chart(fig, use_container_width=True)
    h = bad.groupby(["defect_name", "customer_name"]).size().reset_index(name="จำนวน")
    st.plotly_chart(px.density_heatmap(h, x="customer_name", y="defect_name", z="จำนวน", histfunc="sum", color_continuous_scale="Reds"), use_container_width=True)
    lots = df.groupby(["lot_key", "customer_name", "production_line"]).agg(units=("inspection_id","count"), defects=("is_defect","sum")).reset_index()
    lots["อัตราตำหนิ %"] = lots.defects / lots.units * 100
    st.dataframe(lots.sort_values("อัตราตำหนิ %", ascending=False).head(10), hide_index=True, use_container_width=True)

def page3():
    df = filtered("manual", 0)
    if nothing(df): return
    bad = df[df.is_defect == 1].copy(); bad["miss"] = bad.final_decision.eq("PASS").astype(int)
    first=bad[bad.hour_in_shift==1].miss.mean(); late=bad[bad.hour_in_shift.between(8,10)].miss.mean()
    ratio=late/first if first and pd.notna(first) else 0
    header("3 · ทำไมคนพลาด", f"ชั่วโมง 8–10 อัตราพลาดเป็น {ratio:.1f} เท่าของชั่วโมงแรก (ข้อมูลจำลอง)")
    hour = bad.groupby(["hour_in_shift", "shift_name"]).miss.mean().reset_index(name="อัตราพลาด")
    st.plotly_chart(px.line(hour, x="hour_in_shift", y="อัตราพลาด", color="shift_name", markers=True), use_container_width=True)
    c1,c2 = st.columns(2)
    exp = bad.groupby("experience_band").miss.mean().reset_index(name="อัตราพลาด")
    c1.plotly_chart(px.bar(exp, x="experience_band", y="อัตราพลาด", color="experience_band"), use_container_width=True)
    defect = bad.groupby("defect_name").miss.mean().reset_index(name="อัตราพลาด").sort_values("อัตราพลาด")
    c2.plotly_chart(px.bar(defect, x="อัตราพลาด", y="defect_name", orientation="h", color="อัตราพลาด", color_continuous_scale="Reds"), use_container_width=True)

def page4():
    f = st.session_state.filters
    manual = filtered("manual", 0); assisted = filtered("assisted", f["scenario"])
    if nothing(manual) or nothing(assisted): return
    km,ka = rates(manual), rates(assisted)
    header("4 · ทางออก 3Eyes", f"สถานการณ์ {f['scenario_name']}: Escape PPM เปลี่ยนจาก {km['ppm']:,.0f} เป็น {ka['ppm']:,.0f}")
    x,y = st.columns(2); x.metric("ของเสียหลุด · manual", f"{km['escaped']:,}", f"{km['ppm']:,.0f} PPM"); y.metric("ของเสียหลุด · assisted", f"{ka['escaped']:,}", f"{ka['ppm']:,.0f} PPM", delta=f"{ka['ppm']-km['ppm']:,.0f} PPM")
    funnel = pd.DataFrame([{"ระบบ":"Manual","ตรวจแล้ว":km["units"],"จับตำหนิได้":km["caught"],"หลุด":km["escaped"]},{"ระบบ":"3Eyes ช่วยคัดกรอง","ตรวจแล้ว":ka["units"],"จับตำหนิได้":ka["caught"],"หลุด":ka["escaped"]}])
    st.plotly_chart(px.bar(funnel.melt(id_vars="ระบบ", var_name="ขั้น", value_name="ชิ้น"), x="ระบบ", y="ชิ้น", color="ขั้น", barmode="group"), use_container_width=True)
    recall = pd.concat([manual.assign(กลุ่ม="Manual"), assisted.assign(กลุ่ม="3Eyes")]).query("is_defect == 1").groupby(["defect_name","กลุ่ม"]).final_decision.apply(lambda s:(s=="FAIL").mean()).reset_index(name="Recall")
    st.plotly_chart(px.bar(recall, x="defect_name", y="Recall", color="กลุ่ม", barmode="group"), use_container_width=True)
    a,b,c = st.columns(3); a.metric("เวลาเฉลี่ยต่อตัว", f"{ka['avg_seconds']:.1f} วินาที"); b.metric("อัตราเตือนผิด", f"{ka['false_alarm']:.1%}"); c.metric("Uncertain", f"{ka['uncertain']:.1%}")

def page5():
    f = st.session_state.filters
    params = assumptions()
    manual = filtered("manual", 0)
    if nothing(manual): return
    header("5 · ความคุ้มค่า", "เปรียบเทียบต้นทุนสะสมและช่วงคืนทุนตามสามสถานการณ์")
    device_total = params["device_unit_price"] * params["device_count"]
    monthly_opex = params["device_subscription_per_month"] * params["device_count"]
    scenarios = query("SELECT scenario_key,scenario_name FROM dim_scenario WHERE scenario_key>0 ORDER BY scenario_key")
    rows=[]; projection=[]; units=max(1,len(manual))
    manual_claim=claim_cost(manual,0)
    manual_per=(manual_claim+manual.inspect_seconds.sum()*params["labor_cost_per_hour"]/3600)/units
    for s in scenarios.itertuples(index=False):
        ad=filtered("assisted",int(s.scenario_key)); ka=rates(ad)
        claims=claim_cost(ad,int(s.scenario_key))
        assisted_per=(claims+ad.inspect_seconds.sum()*params["labor_cost_per_hour"]/3600)/max(1,len(ad))
        monthly_saving=(manual_per-assisted_per)*len(manual)/6-monthly_opex
        payback=device_total/monthly_saving if monthly_saving>0 else float("inf")
        net_saving=monthly_saving*6-device_total
        rows.append({"สถานการณ์":s.scenario_name,"Escape PPM":round(ka["ppm"]),"False alarm":f"{ka['false_alarm']:.1%}","Uncertain":f"{ka['uncertain']:.1%}","Override":f"{ka['overrides']/ka['device_fail']:.1%}" if ka['device_fail'] else "0.0%","ประหยัดสุทธิ/6 เดือน":net_saving,"ROI/6 เดือน":net_saving/device_total if device_total else 0,"คืนทุน (เดือน)":payback})
        for month in range(25):
            projection.append({"เดือน":month,"ต้นทุนรวมพร้อมอุปกรณ์":device_total+(monthly_opex+assisted_per*len(manual)/6)*month,
                "ต้นทุนหากไม่มีอุปกรณ์":manual_per*len(manual)/6*month,"สถานการณ์":s.scenario_name})
    df=pd.DataFrame(rows)
    months=sorted(x for x in df["คืนทุน (เดือน)"].tolist() if pd.notna(x) and x != float("inf"))
    if months: st.subheader(f"ช่วงคืนทุนในสถานการณ์ที่คุ้มทุน: {min(months):.1f}–{max(months):.1f} เดือน")
    else: st.subheader("ภายใต้สมมติฐานนี้ยังไม่พบสถานการณ์ที่คืนทุนได้")
    st.dataframe(df.style.format({"ประหยัดสุทธิ/6 เดือน":"฿{:,.0f}","คืนทุน (เดือน)":"{:.1f}"}),hide_index=True,use_container_width=True)
    chosen=pd.DataFrame(projection).query("สถานการณ์ == @f['scenario_name']")
    st.plotly_chart(px.line(chosen,x="เดือน",y=["ต้นทุนรวมพร้อมอุปกรณ์","ต้นทุนหากไม่มีอุปกรณ์"],markers=True),use_container_width=True)
    st.caption(f"ลงทุนเริ่มต้น {fmt_thb(device_total)} · ค่าสมาชิกรายเดือน {fmt_thb(monthly_opex)} · ใช้สมมติฐานจาก config/assumptions.csv")
    st.markdown("#### ทดลองระดับความเข้มงวด")
    strict=st.slider("Strictness",1,5,3); base=rates(filtered("assisted",f["scenario"]))
    recall=max(0,min(1,base["recall"]+(strict-3)*params["strictness_recall_delta_per_step"])); false=max(0,base["false_alarm"]-(strict-3)*params["strictness_false_alarm_delta_per_step"])
    st.write(f"ค่าจำลองตาม strictness {strict}: Recall ประมาณ **{recall:.1%}**, False alarm ประมาณ **{false:.1%}**")

def main():
    if not DB.exists(): st.error("ยังไม่พบฐานข้อมูล โปรดรัน `python run.py all` ก่อนเปิด Dashboard"); st.stop()
    st.session_state.filters=filters()
    pages={"1 · ปัญหา":page1,"2 · ตำหนิอยู่ตรงไหน":page2,"3 · ทำไมคนพลาด":page3,"4 · ทางออก 3Eyes":page4,"5 · ความคุ้มค่า":page5}
    pages[st.sidebar.radio("ตอนของเรื่อง",list(pages))]()
    st.divider(); st.caption(DISCLAIMER)

if __name__ == "__main__": main()
