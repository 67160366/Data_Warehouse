# แผนงาน: Narrative Dashboard — ธุรกิจ "ตาที่ 3" (3Eyes)

วิชา Data Warehouse × วิชา Business Idea Creation
Repo อ้างอิง: `3eyes-anomaly-detection` (ฝั่งธุรกิจ/โมเดล) และ `Data_Warehouse` (งาน ETL/Star Schema เดิม)

---

## 0. สรุปภาพรวม

| หัวข้อ | รายละเอียด |
|---|---|
| โจทย์ | ออกแบบ Dashboard เชิงเล่าเรื่องที่เกี่ยวข้องกับธุรกิจ "ตาที่ 3" อุปกรณ์สวมติดตัวช่วย QC คัดกรองน็อต |
| สิ่งที่ต้องส่ง | (1) Data ที่ใช้ (2) Dashboard (3) รายชื่อกลุ่ม — ส่งเป็น Repository |
| แนวทาง | สร้างข้อมูลจำลอง (simulated) → โหลดเข้า SQLite แบบ Star Schema ด้วย ETL pipeline → สร้าง KPI views → Dashboard เล่าเรื่อง 5 ตอน |
| เครื่องมือหลัก | Python ≥ 3.11, pandas, numpy, SQLite, Streamlit + Plotly (ทางเลือก: Power BI อ่านจาก CSV/SQLite เดียวกัน) |
| ประเด็นความซื่อสัตย์ของข้อมูล | ข้อมูลเป็น **ข้อมูลจำลอง** ที่อิงพารามิเตอร์จริงของโปรเจค (ตำหนิ 8 ประเภท, น็อตหัวหกเหลี่ยมมีบ่าชุบสังกะสี, อุปกรณ์สวมใส่ที่คุมแสง/มุมไม่ได้) ต้องระบุบน Dashboard และ README ว่าเป็นข้อมูลจำลอง และตัวเลขความแม่นยำของอุปกรณ์เป็น **สมมติฐานเชิงสถานการณ์** ไม่ใช่ผลทดสอบจริง (repo 3Eyes ระบุว่ายังไม่ควรเคลมความแม่นยำ) |

### 0.1 ข้อความหลักที่ Dashboard ต้องเล่า (Storyline ย่อ)

> โรงงานผลิตน็อตที่ใช้คน QC ตรวจด้วยตาอย่างเดียวมีของเสียหลุดถึงลูกค้า ซึ่งเกิดจากตำหนิบางประเภทที่ตรวจยาก และจากความล้าปลายกะ
> เมื่อใช้ 3Eyes เป็นด่านคัดกรองสุดท้ายร่วมกับคน ของเสียที่หลุดลดลงภายใต้สมมติฐานที่กำหนด และอุปกรณ์คุ้มทุนภายในระยะเวลาที่คำนวณได้

---

## 1. โครงสร้างไฟล์ใน Repository

ชื่อ repo ที่แนะนำ: `3eyes-dw-dashboard`

```
3eyes-dw-dashboard/
├── README.md                     # ภาพรวม, รายชื่อกลุ่ม, วิธีรัน, ข้อสมมติ, ข้อจำกัด
├── requirements.txt
├── run.sh / run.ps1              # สั่งรันทุกขั้นตอน (setup, data, etl, validate, app)
├── .gitignore                    # ไม่ commit .venv, *.db (หรือ commit db ตัวอย่างขนาดเล็กตามที่ตกลง)
│
├── config/
│   ├── assumptions.csv           # ค่าสมมติฐานทั้งหมด (ราคา ค่าเคลม ค่าแรง recall ตามสถานการณ์) พร้อมแหล่งอ้างอิง
│   └── generator_params.yaml     # พารามิเตอร์การสร้างข้อมูล (seed, จำนวน lot, สัดส่วนตำหนิ ฯลฯ)
│
├── data/
│   ├── raw/                      # CSV ที่สร้างจากสคริปต์ (ส่งงานส่วน "Data ที่ใช้")
│   │   ├── dim_date.csv
│   │   ├── dim_shift.csv
│   │   ├── dim_inspector.csv
│   │   ├── dim_device.csv
│   │   ├── dim_lot.csv
│   │   ├── dim_defect.csv
│   │   ├── dim_scenario.csv
│   │   ├── fact_inspection.csv
│   │   └── fact_customer_claim.csv
│   ├── warehouse/
│   │   └── threeeyes_dw.db       # SQLite ที่โหลดเสร็จแล้ว
│   ├── quarantine/               # แถวที่ไม่ผ่าน validation (ถ้ามี) พร้อมเหตุผล
│   └── data_dictionary.md        # อธิบายทุกตาราง ทุกคอลัมน์
│
├── src/
│   ├── generate_data.py          # สร้างข้อมูลจำลองจาก config
│   ├── schema.sql                # DDL ของ Star Schema ทั้งหมด
│   ├── etl/
│   │   ├── 01_create_schema.py
│   │   ├── 02_load_staging.py
│   │   ├── 03_load_dimensions.py
│   │   ├── 04_load_facts.py
│   │   ├── 05_build_marts.py     # สร้าง fact_lot_summary และ views ของ KPI
│   │   ├── 06_validate.py        # data quality checks + reconciliation
│   │   └── common.py             # เชื่อมต่อ DB, logger, run log, quarantine helper
│   └── sql/
│       ├── kpi_views.sql         # CREATE VIEW สำหรับทุก KPI
│       └── queries_dashboard.sql # query ที่ Dashboard เรียกใช้
│
├── dashboard/
│   ├── app.py                    # entry point (Streamlit)
│   ├── pages/
│   │   ├── 1_ปัญหา.py
│   │   ├── 2_ตำหนิอยู่ตรงไหน.py
│   │   ├── 3_ทำไมคนพลาด.py
│   │   ├── 4_ทางออก_3Eyes.py
│   │   └── 5_ความคุ้มค่า.py
│   ├── components/               # ฟังก์ชันวาดกราฟ, KPI card, ธีมสี
│   └── assets/                   # โลโก้, รูปประกอบ
│
├── tests/
│   ├── test_generator.py         # ตรวจว่าข้อมูลที่สร้างตรงกับ params (สัดส่วน, ช่วงค่า)
│   ├── test_etl.py               # รัน ETL ซ้ำแล้วผลต้องเท่าเดิม (idempotent)
│   └── test_kpi.py               # KPI ที่คำนวณด้วย SQL ตรงกับ pandas คำนวณมือ
│
├── docs/
│   ├── 01_business_context.md    # โยงกับ BMC / market ของ 3Eyes
│   ├── 02_storyboard.md          # ภาพร่าง Dashboard ทีละหน้า + ประโยคหัวข้อ
│   ├── 03_kpi_definitions.md     # สูตร KPI ฉบับเต็ม
│   ├── 04_etl_design.md          # แผนผัง pipeline, ลำดับการโหลด, กติกา quarantine
│   └── screenshots/              # ภาพหน้าจอ Dashboard สำหรับส่งงาน
│
└── reports/
    ├── etl_run_log.csv           # export จากตาราง etl_run_log
    └── data_quality_report.md    # สร้างอัตโนมัติจาก 06_validate.py
```

หลักการ: ตัวเลขทุกตัวบน Dashboard ต้องมาจาก query/สคริปต์ ไม่พิมพ์ด้วยมือ (ตรงกับกติกาของ repo 3Eyes)

---

## 2. การออกแบบข้อมูล (Star Schema)

### 2.1 แผนผังความสัมพันธ์

```
                 dim_date ──┐
                dim_shift ──┤
            dim_inspector ──┤
               dim_device ──┼──► fact_inspection ◄── dim_defect (true_defect_key)
                  dim_lot ──┤            │
             dim_scenario ──┘            │ (ผลรวมต่อ lot + ประเภทตำหนิ)
                                         ▼
                            fact_customer_claim  ──► fact_lot_summary (mart สร้างจาก SQL)
```

### 2.2 Grain ของตาราง Fact

| ตาราง | Grain (1 แถว =) |
|---|---|
| `fact_inspection` | น็อต 1 ตัวที่ถูกตรวจ 1 ครั้ง |
| `fact_customer_claim` | เคลม 1 รายการ ต่อ lot ต่อประเภทตำหนิ |
| `fact_lot_summary` | 1 lot (snapshot สรุป สร้างจาก SQL ไม่ใช่ข้อมูลดิบ) |

### 2.3 DDL (ไฟล์ `src/schema.sql`)

```sql
PRAGMA foreign_keys = ON;

-- ============ DIMENSIONS ============
CREATE TABLE IF NOT EXISTS dim_date (
    date_key        INTEGER PRIMARY KEY,         -- รูปแบบ YYYYMMDD
    full_date       TEXT NOT NULL,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT NOT NULL,
    week_of_year    INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,            -- 1=จันทร์
    is_weekend      INTEGER NOT NULL CHECK (is_weekend IN (0,1)),
    period_phase    TEXT NOT NULL CHECK (period_phase IN ('baseline_manual','assisted_3eyes'))
);

CREATE TABLE IF NOT EXISTS dim_shift (
    shift_key       INTEGER PRIMARY KEY,
    shift_name      TEXT NOT NULL,               -- เช้า / บ่าย / ดึก
    start_hour      INTEGER NOT NULL,
    end_hour        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_inspector (
    inspector_key   INTEGER PRIMARY KEY,
    inspector_code  TEXT NOT NULL UNIQUE,        -- เช่น QC-001 (ไม่ใช้ชื่อจริง)
    tenure_years    REAL NOT NULL,
    experience_band TEXT NOT NULL                -- <1 ปี / 1-3 ปี / >3 ปี
);

CREATE TABLE IF NOT EXISTS dim_device (
    device_key      INTEGER PRIMARY KEY,
    device_code     TEXT NOT NULL UNIQUE,        -- เช่น 3EYES-01
    model_version   TEXT NOT NULL,
    deployed_date   TEXT
);

CREATE TABLE IF NOT EXISTS dim_lot (
    lot_key         INTEGER PRIMARY KEY,
    lot_code        TEXT NOT NULL UNIQUE,
    customer_name   TEXT NOT NULL,
    production_line TEXT NOT NULL,
    lot_size        INTEGER NOT NULL CHECK (lot_size > 0),
    production_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_defect (
    defect_key      INTEGER PRIMARY KEY,
    defect_name     TEXT NOT NULL UNIQUE,        -- 8 ประเภทตาม docs/00_BRIEF.md
    defect_group    TEXT NOT NULL,               -- ดี / ผิวเกลียว / บ่า-หัว / หกเหลี่ยม / ทั่วผิว
    location        TEXT NOT NULL,               -- ตำแหน่งที่พบ
    severity        TEXT NOT NULL CHECK (severity IN ('none','minor','major','critical')),
    is_defect       INTEGER NOT NULL CHECK (is_defect IN (0,1))
);

CREATE TABLE IF NOT EXISTS dim_scenario (
    scenario_key    INTEGER PRIMARY KEY,         -- 0 = ใช้ร่วมทุกสถานการณ์ (ช่วง manual)
    scenario_name   TEXT NOT NULL,               -- N/A, Conservative, Base, Optimistic
    description     TEXT
);

-- ============ FACTS ============
CREATE TABLE IF NOT EXISTS fact_inspection (
    inspection_id     INTEGER PRIMARY KEY,
    date_key          INTEGER NOT NULL REFERENCES dim_date(date_key),
    shift_key         INTEGER NOT NULL REFERENCES dim_shift(shift_key),
    inspector_key     INTEGER NOT NULL REFERENCES dim_inspector(inspector_key),
    device_key        INTEGER REFERENCES dim_device(device_key),      -- NULL เมื่อ manual
    lot_key           INTEGER NOT NULL REFERENCES dim_lot(lot_key),
    scenario_key      INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    true_defect_key   INTEGER NOT NULL REFERENCES dim_defect(defect_key),   -- ผลจริงจากการตรวจซ้ำ (ground truth)
    inspection_mode   TEXT NOT NULL CHECK (inspection_mode IN ('manual','assisted')),
    hour_in_shift     INTEGER NOT NULL CHECK (hour_in_shift BETWEEN 1 AND 12),
    lighting_cond     TEXT NOT NULL CHECK (lighting_cond IN ('good','dim','glare')),
    device_decision   TEXT CHECK (device_decision IN ('PASS','FAIL','UNCERTAIN')),   -- NULL เมื่อ manual
    anomaly_score     REAL,                                           -- NULL เมื่อ manual
    strictness_level  INTEGER CHECK (strictness_level BETWEEN 1 AND 5),
    final_decision    TEXT NOT NULL CHECK (final_decision IN ('PASS','FAIL')),
    override_flag     INTEGER NOT NULL DEFAULT 0 CHECK (override_flag IN (0,1)),
    inspect_seconds   REAL NOT NULL CHECK (inspect_seconds > 0)
);

CREATE TABLE IF NOT EXISTS fact_customer_claim (
    claim_id          INTEGER PRIMARY KEY,
    date_key          INTEGER NOT NULL REFERENCES dim_date(date_key),
    lot_key           INTEGER NOT NULL REFERENCES dim_lot(lot_key),
    defect_key        INTEGER NOT NULL REFERENCES dim_defect(defect_key),
    scenario_key      INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    qty_returned      INTEGER NOT NULL CHECK (qty_returned >= 0),
    claim_cost        REAL NOT NULL CHECK (claim_cost >= 0),
    rework_cost       REAL NOT NULL CHECK (rework_cost >= 0)
);

-- ============ MART (สร้างจาก SQL หลังโหลด fact) ============
CREATE TABLE IF NOT EXISTS fact_lot_summary (
    lot_key           INTEGER NOT NULL REFERENCES dim_lot(lot_key),
    scenario_key      INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    inspection_mode   TEXT NOT NULL,
    units_inspected   INTEGER NOT NULL,
    true_defects      INTEGER NOT NULL,
    defects_caught    INTEGER NOT NULL,
    defects_escaped   INTEGER NOT NULL,
    false_alarms      INTEGER NOT NULL,
    labor_cost        REAL NOT NULL,
    claim_cost        REAL NOT NULL,
    PRIMARY KEY (lot_key, scenario_key, inspection_mode)
);

-- ============ OPERATIONAL TABLES (ETL) ============
CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    step_name     TEXT NOT NULL,
    rows_read     INTEGER,
    rows_loaded   INTEGER,
    rows_rejected INTEGER,
    status        TEXT NOT NULL CHECK (status IN ('success','failed','partial')),
    message       TEXT
);

CREATE TABLE IF NOT EXISTS etl_quarantine (
    quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES etl_run_log(run_id),
    source_table  TEXT NOT NULL,
    raw_row_json  TEXT NOT NULL,
    reject_reason TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- ============ INDEXES ============
CREATE INDEX IF NOT EXISTS ix_fi_date      ON fact_inspection(date_key);
CREATE INDEX IF NOT EXISTS ix_fi_lot       ON fact_inspection(lot_key);
CREATE INDEX IF NOT EXISTS ix_fi_mode_scn  ON fact_inspection(inspection_mode, scenario_key);
CREATE INDEX IF NOT EXISTS ix_fi_defect    ON fact_inspection(true_defect_key);
CREATE INDEX IF NOT EXISTS ix_fc_lot       ON fact_customer_claim(lot_key);
```

### 2.4 ข้อมูลอ้างอิงของ `dim_defect` (8 แถว ตามที่ทีมจัดกลุ่มไว้)

| defect_key | defect_name | location | is_defect | severity (สมมติ — ทีมต้องยืนยัน) |
|---|---|---|---|---|
| 0 | งานดี | ไม่มีตำหนิ | 0 | none |
| 1 | บ่ากระแทก | บ่า/หน้าแปลนใต้หัว | 1 | minor |
| 2 | แชฟเฟอร์กระแทก | มุมลบคมปลายเกลียว | 1 | minor |
| 3 | เกลียวกระแทก | ผิวเกลียว | 1 | major |
| 4 | เกลียวรูด | เกลียวเสียรูป | 1 | critical |
| 5 | เหลี่ยมเป็นรอย | ผิวหกเหลี่ยม | 1 | minor |
| 6 | เหลี่ยมเสีย | หกเหลี่ยมผิดรูป | 1 | major |
| 7 | สนิม | ทั่วผิว | 1 | major |

### 2.5 ไฟล์สมมติฐาน `config/assumptions.csv`

ทุกบรรทัดต้องมีคอลัมน์ `source` ถ้าไม่มีแหล่งอ้างอิงจริงให้ใส่ `ASSUMPTION` ห้ามปล่อยว่าง และห้ามใช้ตัวเลขที่ไม่มีที่มาโดยไม่ติดป้าย

```csv
param,value,unit,source,note
claim_cost_per_returned_unit,0,THB,ASSUMPTION,แทนด้วยค่าจาก docs/10_MARKET.md หรือการประมาณของทีม
rework_cost_per_returned_unit,0,THB,ASSUMPTION,
labor_cost_per_hour,0,THB,ASSUMPTION,อ้างอิงค่าแรงขั้นต่ำ/เงินเดือน QC ในพื้นที่ EEC (ระบุแหล่ง)
customer_detection_rate,0.60,ratio,ASSUMPTION,สัดส่วนของเสียที่ลูกค้าตรวจพบและเคลม
device_unit_price,0,THB,docs/11_BMC.md,ราคาอุปกรณ์ต่อเครื่อง
device_subscription_per_month,0,THB,docs/11_BMC.md,ถ้ามีรูปแบบ subscription
device_count,0,units,ASSUMPTION,จำนวนเครื่องที่ใช้ในโรงงานจำลอง
```

> ค่า `0` ข้างบนเป็นที่ว่างให้ทีมกรอก ห้ามส่งงานโดยปล่อยเป็น 0

---

## 3. แผนการสร้างข้อมูลจำลอง (`src/generate_data.py`)

### 3.1 พารามิเตอร์หลัก (`config/generator_params.yaml`)

| พารามิเตอร์ | ค่าเริ่มต้นที่เสนอ | หมายเหตุ |
|---|---|---|
| `seed` | 42 | ให้ผลซ้ำได้ |
| ระยะเวลา | 26 สัปดาห์ | 13 สัปดาห์แรก = `baseline_manual`, 13 สัปดาห์หลัง = `assisted_3eyes` |
| จำนวน lot | ~120 | ~4–5 lot ต่อสัปดาห์ |
| น็อตที่ตรวจต่อ lot | สุ่ม 200–600 | ได้ประมาณ 36,000 แถวต่อ 1 ชุดข้อมูล |
| จำนวนพนักงาน QC | 8–12 คน | กระจายอายุงานหลายระดับ |
| จำนวนกะ | 3 กะ | เช้า/บ่าย/ดึก |
| จำนวนอุปกรณ์ | 4–6 เครื่อง | ใช้เฉพาะช่วง assisted |
| อัตราตำหนิเฉลี่ยต่อ lot | ~3% | ให้แต่ละ lot สุ่มจากการแจกแจงเบ้ (เช่น Beta) เพื่อให้บาง lot สูงผิดปกติ |

### 3.2 สัดส่วนประเภทตำหนิ (สมมติ — ปรับได้)

| ประเภท | สัดส่วนในกลุ่มของเสีย |
|---|---|
| สนิม | 25% |
| เกลียวกระแทก | 20% |
| บ่ากระแทก | 15% |
| เหลี่ยมเป็นรอย | 15% |
| แชฟเฟอร์กระแทก | 10% |
| เกลียวรูด | 8% |
| เหลี่ยมเสีย | 7% |

### 3.3 พฤติกรรมของ "คน" (ช่วง manual และการตัดสินสุดท้ายในช่วง assisted)

`P(คนจับตำหนิได้) = base_recall[ประเภท] × fatigue_factor × experience_factor × lighting_factor`

| ปัจจัย | กติกาเสนอ |
|---|---|
| `base_recall` ตามประเภท | ตำหนิเห็นชัดสูงกว่า (เช่น เหลี่ยมเสีย ~0.90) ตำหนิเห็นยาก ต่ำกว่า (เช่น เกลียวรูด ~0.65, สนิมระยะเริ่ม ~0.70) |
| `fatigue_factor` | ลดลงตาม `hour_in_shift` (เช่น ลง ~3% ต่อชั่วโมงหลังชั่วโมงที่ 4) และกะดึกต่ำกว่าเล็กน้อย |
| `experience_factor` | <1 ปี ต่ำกว่า, >3 ปี สูงกว่า |
| `lighting_factor` | `good`=1.0, `dim`=0.9, `glare`=0.9 |
| อัตราตัดสิน FAIL ผิดในน็อตดี | ~1–2% |
| `inspect_seconds` | แจกแจงแบบ lognormal ค่ากลางสมมติ (ต้องระบุใน assumptions) |

### 3.4 พฤติกรรมของ "อุปกรณ์ 3Eyes" ตามสถานการณ์ (ช่วง assisted)

ค่าเหล่านี้เป็น **สมมติฐานเชิงสถานการณ์** ไม่ใช่ผลทดสอบ ต้องติดป้ายบน Dashboard

| สถานการณ์ | device recall (เฉลี่ย) | device false alarm | uncertain rate |
|---|---|---|---|
| Conservative | ~0.75 | ~6% | ~12% |
| Base | ~0.85 | ~4% | ~8% |
| Optimistic | ~0.92 | ~3% | ~6% |

กติกาการตัดสิน (assisted):

1. อุปกรณ์ให้ `device_decision` = PASS / FAIL / UNCERTAIN จาก `anomaly_score` และ `strictness_level`
2. ถ้า FAIL → คนตรวจยืนยัน (ส่วนใหญ่ยืนยัน, บางส่วนกด override = `override_flag=1`)
3. ถ้า UNCERTAIN → ตัดสินด้วยพฤติกรรมคน (3.3)
4. ถ้า PASS → ส่วนใหญ่ตามเครื่อง แต่คนมีโอกาสจับตำหนิที่เครื่องพลาดได้บ้าง
5. ช่วง assisted ให้ `inspect_seconds` ต่ำลงเล็กน้อยสำหรับน็อตที่ PASS ชัดเจน
6. สร้างข้อมูลช่วง assisted ครบทั้ง 3 สถานการณ์ โดยใช้ "น็อตและ true defect ชุดเดียวกัน" เปลี่ยนเฉพาะพฤติกรรมอุปกรณ์ เพื่อเทียบกันได้ตรงๆ (`scenario_key` 1–3) ส่วนช่วง manual ใช้ `scenario_key = 0`

### 3.5 รูปแบบที่ต้องฝังในข้อมูลเพื่อให้เล่าเรื่องได้ (ประกาศไว้ก่อนสร้าง)

- ตำหนิ 2–3 ประเภทมีสัดส่วนรวมสูง (Pareto ชัด)
- ตำหนิบางประเภท (เกลียวรูด, สนิม) คนพลาดสูงกว่าประเภทอื่น
- อัตราพลาดของคนสูงขึ้นปลายกะและในกะดึก
- มี lot 3–5 lot ที่อัตราตำหนิสูงผิดปกติ (เช่น ลูกค้าหรือไลน์ใดไลน์หนึ่ง)
- ช่วง assisted ของเสียที่หลุดลดลงแต่ **ไม่เป็นศูนย์** และมีผลข้างเคียง (false alarm, uncertain) เพื่อให้เรื่องน่าเชื่อถือ

### 3.6 การสร้าง `fact_customer_claim`

ต่อ lot × ประเภทตำหนิ: `qty_returned = round(escaped_units × customer_detection_rate)` (สุ่มเล็กน้อย), `claim_cost = qty_returned × claim_cost_per_returned_unit`, `rework_cost = qty_returned × rework_cost_per_returned_unit` โดยอ่านค่าจาก `assumptions.csv`

### 3.7 ชุดทดสอบของตัวสร้างข้อมูล (`tests/test_generator.py`)

- seed เดิมให้ผลเหมือนเดิมทุกครั้ง
- สัดส่วนตำหนิรวมอยู่ในช่วงที่ตั้งไว้ (±ความคลาดเคลื่อนที่ยอมรับ)
- ไม่มีค่า null ในคอลัมน์ที่กำหนดว่า NOT NULL
- ช่วง manual มี `device_key`, `device_decision`, `anomaly_score` เป็น NULL ทุกแถว
- ช่วง assisted มี `device_decision` ครบทุกแถว

---

## 4. การโหลดเข้า Database (ETL Pipeline)

### 4.1 ภาพรวม

```
data/raw/*.csv
   │  02_load_staging      (อ่านเป็น staging_* ตามต้นฉบับ ไม่แก้ข้อมูล)
   ▼
staging_* tables
   │  03_load_dimensions   (validate → upsert ด้วย natural key)
   ▼
dim_* tables
   │  04_load_facts        (validate FK/ช่วงค่า → แถวไม่ผ่านไป etl_quarantine)
   ▼
fact_inspection, fact_customer_claim
   │  05_build_marts       (สร้าง fact_lot_summary + KPI views)
   ▼
views / marts  ───►  Dashboard
   │  06_validate          (data quality + reconciliation → reports/)
```

ทุกขั้นตอนเขียนผลลงตาราง `etl_run_log` (จำนวนแถวที่อ่าน/โหลด/ปฏิเสธ, สถานะ)

### 4.2 รายละเอียดแต่ละขั้น

**`01_create_schema.py`**
- อ่าน `src/schema.sql` แล้วสร้างตารางทั้งหมดใน `data/warehouse/threeeyes_dw.db`
- เปิด `PRAGMA foreign_keys = ON`
- มีตัวเลือก `--reset` สำหรับลบแล้วสร้างใหม่

**`02_load_staging.py`**
- อ่าน CSV ทุกไฟล์ด้วย pandas โดยระบุ dtype ชัดเจน
- เขียนลงตาราง `stg_<ชื่อไฟล์>` แบบ replace ทุกครั้ง (staging ไม่เก็บประวัติ)
- บันทึกจำนวนแถวต่อไฟล์ลง `etl_run_log`

**`03_load_dimensions.py`**
- โหลด dimension ก่อน fact เสมอ
- ใช้ natural key (`lot_code`, `inspector_code`, `device_code`, `defect_name`) เพื่อ upsert แบบ idempotent (`INSERT ... ON CONFLICT DO UPDATE` หรือ `INSERT OR IGNORE` ตามตาราง)
- ตรวจ: ค่าซ้ำของ natural key, ค่าว่างในคอลัมน์สำคัญ, ค่า enum ที่ไม่ถูกต้อง
- ต้องมีแถว `scenario_key = 0` ('N/A') และ `defect_key = 0` ('งานดี') เสมอ

**`04_load_facts.py`**
- เงื่อนไข validation ต่อแถว `fact_inspection`:
  1. FK ทุกตัวต้องมีใน dimension
  2. `inspection_mode='manual'` → `device_key`, `device_decision`, `anomaly_score` ต้องเป็น NULL และ `scenario_key=0`
  3. `inspection_mode='assisted'` → `device_decision` ต้องไม่ NULL และ `scenario_key` ∈ {1,2,3}
  4. `inspect_seconds > 0`, `hour_in_shift` อยู่ใน 1–12
  5. `override_flag=1` ได้เฉพาะเมื่อ assisted
  6. `final_decision` เป็น PASS/FAIL เท่านั้น
- แถวที่ไม่ผ่านไปเก็บใน `etl_quarantine` พร้อม `reject_reason` ไม่ทำให้ทั้ง pipeline ล้ม
- โหลดเป็น batch (`executemany`) ใน transaction เดียว ถ้ามีข้อผิดพลาดร้ายแรงให้ rollback และบันทึก `status='failed'`
- **Idempotent:** ใช้ `inspection_id` เป็นคีย์ รันซ้ำแล้วไม่เกิดแถวซ้ำ (`INSERT OR REPLACE` หรือ upsert)

**`05_build_marts.py`**
- ลบแล้วสร้าง `fact_lot_summary` ใหม่จาก `fact_inspection` + `fact_customer_claim` + `assumptions.csv` (คำนวณ `labor_cost` จาก `inspect_seconds × labor_cost_per_hour / 3600`)
- รันไฟล์ `src/sql/kpi_views.sql` เพื่อสร้าง/อัปเดต views

**`06_validate.py`** (ผลสรุปเขียนเป็น `reports/data_quality_report.md`)

| ประเภท | ตัวอย่างการตรวจ |
|---|---|
| Completeness | ไม่มี NULL ในคอลัมน์ NOT NULL |
| Uniqueness | `inspection_id`, `lot_code` ไม่ซ้ำ |
| Referential integrity | ไม่มี FK กำพร้า (`PRAGMA foreign_key_check`) |
| Reconciliation | จำนวนแถวใน CSV = โหลด + quarantine; จำนวนน็อตต่อ lot ≤ `lot_size` |
| Consistency | `defects_caught + defects_escaped = true_defects` ในทุก lot |
| Business rule | ช่วง assisted ไม่มีแถว manual ในช่วงวันที่ assisted (และกลับกัน) |
| Reproducibility | รัน pipeline สองรอบ ผลรวมของ KPI ต้องเท่ากัน |

### 4.3 คำสั่งรันทั้งหมด (`run.sh` / `run.ps1`)

```
setup     # สร้าง venv, pip install -r requirements.txt
data      # python src/generate_data.py
etl       # รัน 01 → 06 ตามลำดับ
test      # pytest tests -q
app       # streamlit run dashboard/app.py
all       # setup → data → etl → test (แล้วเปิด app ตามต้องการ)
```

---

## 5. KPI (นิยามและ SQL)

คำจำกัดความกลาง (ใช้ทุก KPI):

- **ของเสียจริง** = `true_defect_key != 0`
- **จับได้ (caught)** = ของเสียจริง และ `final_decision = 'FAIL'`
- **หลุด (escaped)** = ของเสียจริง และ `final_decision = 'PASS'`
- **เตือนผิด (false alarm)** = น็อตดี (`true_defect_key = 0`) และ `final_decision = 'FAIL'`
- แบ่งเปรียบเทียบด้วย `inspection_mode` และ `scenario_key` เสมอ

### 5.1 ตาราง KPI

| # | KPI | สูตร | ตอนของเรื่อง | ความหมายที่บอก |
|---|---|---|---|---|
| K1 | **Defect Escape Rate (PPM)** | escaped ÷ units ที่ final=PASS × 1,000,000 | 1, 4 | KPI หลัก — ของเสียหลุดถึงลูกค้ากี่ชิ้นต่อล้าน |
| K2 | **Detection Recall (final)** | caught ÷ ของเสียจริง | 3, 4 | ระบบโดยรวมจับตำหนิได้กี่ % |
| K3 | **Recall by Defect Type** | K2 แยกตาม `defect_name` | 2, 4 | ประเภทไหนจับยาก |
| K4 | **Human Miss Rate by Hour** | 1 − recall แยกตาม `hour_in_shift` (เฉพาะ manual) | 3 | ความล้าทำให้พลาดมากขึ้น |
| K5 | **False Alarm Rate** | false alarm ÷ น็อตดีทั้งหมด | 4, 5 | ภาระงานเกินจำเป็นของพนักงาน |
| K6 | **Device Uncertain Rate** | device_decision = UNCERTAIN ÷ assisted ทั้งหมด | 4, 5 | ส่วนที่ต้องพึ่งการตัดสินของคน |
| K7 | **Override Rate** | override_flag = 1 ÷ แถวที่เครื่องตอบ FAIL | 5 | ความเชื่อใจ/คุณภาพของโมเดลในสายตา QC |
| K8 | **Avg Inspection Time / Throughput** | AVG(inspect_seconds); 3600 ÷ AVG | 4 | ประสิทธิภาพต่อตัวและต่อชั่วโมง |
| K9 | **Defect Rate by Lot/Customer** | ของเสียจริง ÷ units ต่อ lot | 2 | lot/ลูกค้าไหนมีปัญหา |
| K10 | **Cost of Quality** | claim_cost + rework_cost + labor_cost | 1, 5 | ต้นทุนรวมของคุณภาพ |
| K11 | **Cost Saving (Assisted vs Manual)** | K10(manual, ต่อหน่วย) − K10(assisted, ต่อหน่วย) แล้วคูณปริมาณ | 5 | ประหยัดได้เท่าไร |
| K12 | **ROI / Payback Period** | (ประหยัดสะสม − ต้นทุนอุปกรณ์) ÷ ต้นทุนอุปกรณ์; payback = ต้นทุนอุปกรณ์ ÷ ประหยัดต่อเดือน | 5 | ความคุ้มค่าของอุปกรณ์ |

หมายเหตุสำคัญ: เปรียบเทียบ manual กับ assisted ด้วยปริมาณหรืออัตราต่อหน่วยที่ปรับให้เทียบกันได้ (ไม่เทียบยอดรวมตรงๆ ถ้าจำนวนน็อตสองช่วงต่างกัน)

### 5.2 ตัวอย่าง SQL (ไฟล์ `src/sql/kpi_views.sql`)

```sql
-- K1/K2/K5/K6/K7/K8: KPI รายสัปดาห์ แยก mode และ scenario
CREATE VIEW IF NOT EXISTS vw_kpi_weekly AS
SELECT
    d.year, d.week_of_year, d.period_phase,
    f.inspection_mode, f.scenario_key,
    COUNT(*)                                                         AS units_inspected,
    SUM(CASE WHEN f.true_defect_key != 0 THEN 1 ELSE 0 END)          AS true_defects,
    SUM(CASE WHEN f.true_defect_key != 0 AND f.final_decision='FAIL' THEN 1 ELSE 0 END) AS caught,
    SUM(CASE WHEN f.true_defect_key != 0 AND f.final_decision='PASS' THEN 1 ELSE 0 END) AS escaped,
    SUM(CASE WHEN f.true_defect_key  = 0 AND f.final_decision='FAIL' THEN 1 ELSE 0 END) AS false_alarms,
    SUM(CASE WHEN f.true_defect_key  = 0 THEN 1 ELSE 0 END)          AS good_units,
    SUM(CASE WHEN f.final_decision='PASS' THEN 1 ELSE 0 END)         AS passed_units,
    SUM(CASE WHEN f.device_decision='UNCERTAIN' THEN 1 ELSE 0 END)   AS uncertain_units,
    SUM(CASE WHEN f.device_decision='FAIL' THEN 1 ELSE 0 END)        AS device_fail_units,
    SUM(f.override_flag)                                             AS overrides,
    AVG(f.inspect_seconds)                                           AS avg_seconds
FROM fact_inspection f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.year, d.week_of_year, d.period_phase, f.inspection_mode, f.scenario_key;

-- ใช้ใน Dashboard: คำนวณอัตราจาก view ด้านบน เช่น
-- escape_ppm     = 1e6 * escaped / passed_units
-- recall         = caught / true_defects
-- false_alarm    = false_alarms / good_units
-- uncertain_rate = uncertain_units / units_inspected     (เฉพาะ assisted)
-- override_rate  = overrides / device_fail_units

-- K3: recall แยกประเภทตำหนิ
CREATE VIEW IF NOT EXISTS vw_recall_by_defect AS
SELECT
    df.defect_name, f.inspection_mode, f.scenario_key,
    COUNT(*) AS defects,
    SUM(CASE WHEN f.final_decision='FAIL' THEN 1 ELSE 0 END) AS caught,
    1.0 * SUM(CASE WHEN f.final_decision='FAIL' THEN 1 ELSE 0 END) / COUNT(*) AS recall
FROM fact_inspection f
JOIN dim_defect df ON df.defect_key = f.true_defect_key
WHERE df.is_defect = 1
GROUP BY df.defect_name, f.inspection_mode, f.scenario_key;

-- K4: อัตราพลาดของคนตามชั่วโมงในกะ (เฉพาะ manual)
CREATE VIEW IF NOT EXISTS vw_human_miss_by_hour AS
SELECT
    f.hour_in_shift, s.shift_name,
    COUNT(*) AS defects,
    1.0 * SUM(CASE WHEN f.final_decision='PASS' THEN 1 ELSE 0 END) / COUNT(*) AS miss_rate
FROM fact_inspection f
JOIN dim_shift s ON s.shift_key = f.shift_key
WHERE f.inspection_mode='manual' AND f.true_defect_key != 0
GROUP BY f.hour_in_shift, s.shift_name;

-- K9: อัตราตำหนิต่อ lot
CREATE VIEW IF NOT EXISTS vw_defect_rate_by_lot AS
SELECT
    l.lot_code, l.customer_name, l.production_line,
    COUNT(*) AS units,
    1.0 * SUM(CASE WHEN f.true_defect_key != 0 THEN 1 ELSE 0 END) / COUNT(*) AS defect_rate
FROM fact_inspection f
JOIN dim_lot l ON l.lot_key = f.lot_key
WHERE f.inspection_mode='manual' OR f.scenario_key = 1   -- นับน็อตชุดเดียวกันครั้งเดียว (ปรับตามที่ออกแบบ)
GROUP BY l.lot_code, l.customer_name, l.production_line;
```

> ระวังการนับซ้ำ: ช่วง assisted มี 3 scenario ที่ใช้น็อตชุดเดียวกัน จึงต้องกรอง `scenario_key` ในทุก query ที่นับจำนวนน็อตหรืออัตราตำหนิของ lot (เขียน test ยืนยัน)

### 5.3 ตัวเลือก KPI ที่เพิ่มได้ถ้ามีเวลา

- Precision (ในกลุ่มที่เตือน FAIL เป็นของเสียจริงกี่ %)
- Defect Severity-weighted Escape (ถ่วงน้ำหนักตามความรุนแรง critical/major/minor)
- Recall ตามสภาพแสง (`lighting_cond`) เพื่อสะท้อนข้อจำกัดของอุปกรณ์สวมใส่ที่คุมแสงไม่ได้

---

## 6. การออกแบบ Dashboard (5 ตอน)

ธีม: ใช้ `st.set_page_config(layout="wide")`, สีคงที่ 2–3 สี (เช่น แดง = ปัญหา/ของเสีย, น้ำเงิน/เขียว = 3Eyes/ทางออก), ฟอนต์ไทยที่อ่านง่าย
Sidebar filter ร่วมทุกหน้า: ช่วงวันที่, ลูกค้า/ไลน์, `scenario` (Conservative/Base/Optimistic), กะ
แถบข้อความด้านล่างทุกหน้า: "ข้อมูลจำลองเพื่อการศึกษา — ค่าความสามารถของอุปกรณ์เป็นสมมติฐานเชิงสถานการณ์ ไม่ใช่ผลทดสอบจริง"

| หน้า | ประโยคหัวข้อ (ตัวอย่าง — ต้องมาจากข้อมูลจริงในชุดที่สร้าง) | องค์ประกอบ | KPI |
|---|---|---|---|
| **1. ปัญหา** | "ของเสียหลุดถึงลูกค้า X ชิ้นต่อล้าน คิดเป็นต้นทุน Y บาทต่อไตรมาส" | KPI card 3–4 ใบ, กราฟเส้นแนวโน้มรายสัปดาห์ของ escape PPM และ cost of quality (ช่วง manual) | K1, K10 |
| **2. ตำหนิอยู่ตรงไหน** | "ตำหนิ 3 ประเภทแรกคิดเป็น Z% ของของเสีย" | Pareto ของ 7 ประเภทตำหนิ + เส้น cumulative %, heatmap ประเภทตำหนิ × ลูกค้า/ไลน์, ตาราง lot ที่อัตราตำหนิสูงสุด 10 อันดับ | K9, K3 (manual) |
| **3. ทำไมคนพลาด** | "ชั่วโมงที่ 8–10 ของกะ คนพลาดมากกว่าชั่วโมงแรกถึง N เท่า" | เส้น miss rate ตาม hour_in_shift แยกกะ, แท่ง miss rate ตามอายุงาน, แท่ง miss rate ตามประเภทตำหนิ | K4, K3 |
| **4. ทางออก 3Eyes** | "เมื่อมี 3Eyes ของเสียที่หลุดลดจาก A เหลือ B (สถานการณ์ Base)" | funnel (ตรวจ → เตือน → ยืนยัน → หลุด) manual vs assisted, แท่ง recall แยกประเภท before/after, KPI card เวลาต่อตัวและ throughput | K1, K2, K3, K8 |
| **5. ความคุ้มค่า** | "คืนทุนภายใน M เดือน (Base) ช่วงตั้งแต่ N ถึง M ตามสถานการณ์" | กราฟต้นทุนสะสม 2 เส้น (ไม่มี/มีอุปกรณ์) พร้อมจุดตัด, ตาราง 3 สถานการณ์, slider `strictness` แสดง trade-off recall กับ false alarm, KPI uncertain/override | K5, K6, K7, K11, K12 |

หลักการเล่าเรื่อง:

- ทุกหน้ามีประโยคสรุปที่สร้างจากข้อมูลด้วยโค้ด (f-string จาก query) ไม่เขียนตัวเลขตายตัว
- ลำดับ: ปัญหา → สาเหตุ → ทางออก → ความคุ้มค่า → (ปิดท้ายด้วยข้อจำกัดและขั้นต่อไป)
- หน้า 5 ต้องแสดง **ช่วงของผลลัพธ์ตามสถานการณ์** ไม่ใช่ตัวเลขเดียว
- เพิ่มกล่อง "ข้อจำกัดของข้อมูล" ที่หน้าสุดท้ายหรือใน sidebar

ภาพร่างของแต่ละหน้า (wireframe) เก็บใน `docs/02_storyboard.md` และภาพหน้าจอจริงเก็บใน `docs/screenshots/`

---

## 7. แผนงานและลำดับการทำ (Task Breakdown)

ระบุผู้รับผิดชอบและวันกำหนดส่งตามจำนวนสมาชิกและกำหนดการของวิชา (คอลัมน์ "ผู้รับผิดชอบ" ให้ทีมกรอก)

### Phase 0 — ตกลงขอบเขตและสมมติฐาน
| # | งาน | ผลลัพธ์ | ผู้รับผิดชอบ |
|---|---|---|---|
| 0.1 | อ่านเงื่อนไขการส่งงานจากอาจารย์ (เครื่องมือ Dashboard ที่ยอมรับ, รูปแบบ repo, กำหนดส่ง) | checklist ข้อกำหนด | |
| 0.2 | ดึงตัวเลขราคา/ต้นทุน/ค่าแรงจาก `docs/10_MARKET.md`, `11_BMC.md` เติม `assumptions.csv` | `config/assumptions.csv` ที่มี source ทุกบรรทัด | |
| 0.3 | ยืนยัน severity และสัดส่วนตำหนิ 8 ประเภท | `dim_defect.csv`, ส่วน 3.2 ในแผนนี้ | |
| 0.4 | เขียน storyboard 5 ตอน | `docs/02_storyboard.md` | |

### Phase 1 — ข้อมูล
| # | งาน | ผลลัพธ์ |
|---|---|---|
| 1.1 | สร้างโครง repo ตามหัวข้อที่ 1 | โฟลเดอร์ + README เปล่า |
| 1.2 | เขียน `generator_params.yaml` | ไฟล์ params |
| 1.3 | เขียน `generate_data.py` ตามหัวข้อที่ 3 | `data/raw/*.csv` |
| 1.4 | เขียน `tests/test_generator.py` และรันผ่าน | ผล pytest |
| 1.5 | เขียน `data/data_dictionary.md` | พจนานุกรมข้อมูล |

### Phase 2 — Data Warehouse และ ETL
| # | งาน | ผลลัพธ์ |
|---|---|---|
| 2.1 | เขียน `schema.sql` และ `01_create_schema.py` | DB ว่างที่มีตารางครบ |
| 2.2 | เขียน `02_load_staging.py`, `03_load_dimensions.py` | dims ถูกโหลด |
| 2.3 | เขียน `04_load_facts.py` พร้อม quarantine + run log | facts ถูกโหลด, `etl_quarantine` ทำงาน |
| 2.4 | เขียน `05_build_marts.py` และ `kpi_views.sql` | `fact_lot_summary` + views |
| 2.5 | เขียน `06_validate.py` และ `tests/test_etl.py` (รันซ้ำแล้วผลเท่าเดิม) | `reports/data_quality_report.md` |
| 2.6 | ทดสอบใส่ข้อมูลเสียโดยตั้งใจ 5–10 แถวเพื่อพิสูจน์ว่า quarantine ทำงาน | หลักฐานสำหรับรายงาน |

### Phase 3 — KPI
| # | งาน | ผลลัพธ์ |
|---|---|---|
| 3.1 | เขียนสูตร KPI ทั้ง 12 ตัวใน `docs/03_kpi_definitions.md` | เอกสารนิยาม |
| 3.2 | เขียน views/queries ใน `src/sql` | views ทำงานได้ |
| 3.3 | `tests/test_kpi.py` เทียบ SQL กับ pandas (กันนับซ้ำจาก 3 scenario) | test ผ่าน |

### Phase 4 — Dashboard
| # | งาน | ผลลัพธ์ |
|---|---|---|
| 4.1 | โครง `app.py` + sidebar filter + ธีมสี | แอปเปิดได้ |
| 4.2 | หน้า 1–2 | หน้าปัญหา และหน้าตำหนิ |
| 4.3 | หน้า 3–4 | หน้าสาเหตุ และหน้าทางออก |
| 4.4 | หน้า 5 + slider strictness + ตารางสถานการณ์ | หน้าความคุ้มค่า |
| 4.5 | ประโยคสรุปอัตโนมัติ, ป้ายข้อมูลจำลอง, กล่องข้อจำกัด | เรื่องเล่าครบ |
| 4.6 | ทดสอบทุก filter ว่ากราฟไม่พังเมื่อไม่มีข้อมูล | ใช้งานได้จริง |

### Phase 5 — ส่งงาน
| # | งาน | ผลลัพธ์ |
|---|---|---|
| 5.1 | เขียน `README.md` (รายชื่อกลุ่ม, วิธีรัน, ข้อสมมติ, ข้อจำกัด, ลิงก์โปรเจค 3Eyes) | README ครบ |
| 5.2 | ถ่ายภาพหน้าจอทุกหน้า | `docs/screenshots/` |
| 5.3 | รัน `all` จากเครื่องสะอาด (clone ใหม่) เพื่อยืนยันว่าทำซ้ำได้ | ยืนยันแล้ว |
| 5.4 | ตรวจ `.gitignore` ไม่มีไฟล์ใหญ่/ความลับ แล้ว push | repo พร้อมส่ง |
| 5.5 | ตรวจ checklist การส่ง (หัวข้อที่ 9) | ผ่านทุกข้อ |

### เส้นทางวิกฤต (ถ้าเวลาจำกัด)

ข้อมูล (Phase 1) → ETL (Phase 2) → KPI views (Phase 3) → หน้า 1, 4, 5 ของ Dashboard
หน้า 2, 3 ทำเพิ่มได้หลังสุด แต่หน้า 3 (ความล้า) เป็นเหตุผลหลักที่ต้องมี "ตาที่ 3" ควรคงไว้ถ้าทำได้

---

## 8. ความเสี่ยงและวิธีรับมือ

| ความเสี่ยง | ผลกระทบ | วิธีรับมือ |
|---|---|---|
| ข้อมูลจำลองถูกมองว่าเป็นผลจริงของโมเดล | เสียความน่าเชื่อถือ | ป้ายข้อมูลจำลองทุกหน้า, ระบุว่า recall เป็นสมมติฐานเชิงสถานการณ์ใน README |
| ตัวเลขต้นทุนไม่มีที่มา | โดนตั้งคำถามตอนนำเสนอ | `assumptions.csv` ต้องมี `source` ทุกบรรทัด ติดป้าย `ASSUMPTION` ถ้าเป็นการประมาณ |
| นับน็อตซ้ำจาก 3 scenario | KPI ผิด | ทุก query กรอง `scenario_key`, เขียน `test_kpi.py` |
| ผลลัพธ์ "สวยเกินจริง" | ขาดความน่าเชื่อถือ | ให้ assisted ยังมี escape, false alarm และ uncertain ที่ไม่เป็นศูนย์ |
| เครื่องมือ Dashboard ไม่ตรงกับที่อาจารย์ต้องการ | ต้องทำใหม่ | ถามอาจารย์ใน Phase 0, เก็บข้อมูลใน SQLite/CSV เพื่อย้ายไป Power BI ได้ |
| รันบนเครื่องอื่นไม่ได้ | ส่งงานไม่ผ่าน | `requirements.txt` ปักเวอร์ชัน, ทดสอบ clone ใหม่ใน Phase 5.3 |

---

## 9. Checklist ก่อนส่ง

**Data ที่ใช้**
- [ ] `data/raw/*.csv` ครบทุกตาราง
- [ ] `data/data_dictionary.md` อธิบายทุกคอลัมน์
- [ ] `config/assumptions.csv` กรอกครบ มี source ทุกบรรทัด
- [ ] สคริปต์สร้างข้อมูลและ seed อยู่ใน repo

**Data Warehouse**
- [ ] `schema.sql` สร้างตารางได้ครบ
- [ ] ETL รันซ้ำแล้วไม่เกิดแถวซ้ำ
- [ ] มี quarantine และ run log
- [ ] `reports/data_quality_report.md` ผ่านทุกข้อ

**Dashboard**
- [ ] 5 ตอนครบ มีประโยคหัวข้อที่สร้างจากข้อมูล
- [ ] KPI ครบตามหัวข้อ 5 (อย่างน้อย K1–K3, K4, K5–K8, K10–K12)
- [ ] มีป้ายข้อมูลจำลองและกล่องข้อจำกัด
- [ ] มีภาพหน้าจอใน `docs/screenshots/`

**รายชื่อกลุ่ม และ Repository**
- [ ] README มีรายชื่อสมาชิก รหัสนักศึกษา และบทบาท
- [ ] README บอกวิธีรันตั้งแต่ clone จนเปิด Dashboard
- [ ] ลิงก์โยงกับโปรเจค `3eyes-anomaly-detection`
- [ ] repo เป็น public หรือแชร์สิทธิ์ให้อาจารย์ตามที่กำหนด

---

## 10. โครง README.md (ร่าง)

```markdown
# 3Eyes Narrative Dashboard (Data Warehouse)

## สมาชิกกลุ่ม
| ชื่อ-สกุล | รหัสนักศึกษา | หน้าที่ |
|---|---|---|

## ที่มาและบริบทธุรกิจ
(โยงกับวิชา Business Idea Creation และ repo 3eyes-anomaly-detection)

## ข้อมูล
- ข้อมูลเป็นข้อมูลจำลอง สร้างด้วย src/generate_data.py (seed = 42)
- ค่าความสามารถของอุปกรณ์เป็นสมมติฐานเชิงสถานการณ์ ไม่ใช่ผลทดสอบจริง
- ตารางทั้งหมด: ดู data/data_dictionary.md

## สถาปัตยกรรม
CSV → staging → dimensions → facts → marts/views → Dashboard

## วิธีรัน
(คำสั่ง setup / data / etl / app)

## KPI
(ตารางย่อ + ลิงก์ docs/03_kpi_definitions.md)

## ภาพหน้าจอ Dashboard
(ฝังภาพจาก docs/screenshots/)

## ข้อจำกัด
(ข้อมูลจำลอง, สมมติฐานต้นทุน, ฯลฯ)
```
