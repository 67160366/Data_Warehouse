# Star Schema

```mermaid
erDiagram
    dim_date ||--o{ fact_inspection : date_key
    dim_shift ||--o{ fact_inspection : shift_key
    dim_inspector ||--o{ fact_inspection : inspector_key
    dim_device o|--o{ fact_inspection : device_key
    dim_lot ||--o{ fact_inspection : lot_key
    dim_defect ||--o{ fact_inspection : true_defect_key
    dim_scenario ||--o{ fact_inspection : scenario_key
    dim_date ||--o{ fact_customer_claim : date_key
    dim_lot ||--o{ fact_customer_claim : lot_key
    dim_defect ||--o{ fact_customer_claim : defect_key
    dim_scenario ||--o{ fact_customer_claim : scenario_key
    dim_shift ||--o{ dim_lot : shift_key
    fact_inspection {
        int inspection_id PK
        string unit_id "same unit across assisted scenarios"
        string inspection_mode
        string final_decision
        float inspect_seconds
    }
    fact_customer_claim {
        int claim_id PK
        int qty_returned
        float claim_cost
        float rework_cost
    }
```

Inspection grain: `unit_id × inspection_mode × scenario_key` (unique). Claim grain: lot × defect × scenario, บันทึกวันเดียวกับ lot; วันที่กะของการตรวจต้องตรง lot. ทั้งสอง facts ใช้ dimensions ร่วมกัน ข้อยกเว้นจาก star แบบบริสุทธิ์คือ `dim_lot.shift_key` เพื่อรับรองกะเดียวกัน

Mart `fact_lot_summary` สรุปหนึ่ง lot × mode × scenario. รวมยอดเคลมต่อ lot/scenario ก่อน join กับการตรวจ ห้าม join facts แบบแถวต่อแถวแล้ว SUM ค่าเคลม
