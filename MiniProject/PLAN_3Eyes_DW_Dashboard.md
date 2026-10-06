# แผนและขอบเขต 3Eyes รุ่นส่งงาน

คำถามหลัก: **อุปกรณ์อาจลดของเสีย แต่คุ้มทุนภายใต้ปริมาณงานและต้นทุนแบบใด?**

ใช้ Streamlit + SQLite และข้อมูลจำลองเพื่อการศึกษา เล่าเรื่องจากมุมโรงงานลูกค้า ผลก่อน–หลังต่างช่วงเวลาไม่ใช่หลักฐานเหตุและผลของอุปกรณ์จริง ห้ามปรับข้อมูลเพื่อบังคับ ROI ให้เป็นบวก

## ขอบเขตที่นำไปใช้

- seed 42, 26 สัปดาห์, 120 lots, 200–600 ตัว/lot; 7 ประเภทตำหนิ + งานดี 1 กลุ่ม
- 7 dimensions, 2 facts; grain น็อตหนึ่งตัวต่อ mode/scenario; assisted 3 สถานการณ์ใช้ `unit_id` และความจริงเดียวกัน
- สุ่มปัจจัยมนุษย์และ random draws ครั้งเดียวก่อนจำลองสถานการณ์; 1 lot อยู่วันและกะเดียว; ชั่วโมง 1–8
- `defect_rate_mean` ควบคุมการแจกแจงจริง; ลูกค้ากระจายข้ามไลน์; ไม่มี anomaly score/strictness
- FAIL และ UNCERTAIN เพิ่มเวลายืนยันตามสมมติฐาน 5 วินาที
- ETL อ่าน staging จริง quarantine ทั้ง inspections/claims และกระทบยอดรอบล่าสุด
- ทุกอัตรามีตัวอย่าง ตัวหาร 0 แสดงคำนวณไม่ได้; แยก Device False Alarm และ Final False Reject
- ROI ใช้ส่วนต่างต้นทุน/ตัว × ปริมาณ/เดือน − ค่าบริการ; baseline จริง 91 วัน; ปรับปริมาณได้; ROI 6 เดือน/กราฟ 24 เดือน
- Dashboard 5 หน้า ตาม [storyboard](docs/02_storyboard.md) พร้อม data lineage และข้อจำกัด

## หลักฐานตรวจรับ

[รายงานคุณภาพ](reports/data_quality_report.md), [ผลทดสอบ](reports/verification.md), [ภาพจริง 5 หน้า](reports/screenshots), [data dictionary](data/data_dictionary.md), [สูตร KPI](docs/03_kpi_definitions.md), [Star Schema](docs/star_schema.md)

ทดสอบ seed ซ้ำ, unit pairing, ETL ซ้ำ, ข้อมูลเสีย 10 แถว, สูตรคำนวณด้วยมือ, ไม่รวม scenario ซ้ำ, 5 หน้าปกติและขอบเขตไม่มีข้อมูล/ไม่มีของเสีย/ไม่มี final PASS/ขาดข้อมูลฝั่งใดฝั่งหนึ่ง รวมทั้งเปิดจากสำเนาส่งงานที่แยกจาก workspace

## การเผยแพร่

เป้าหมาย `67160366/Data_Warehouse`, branch `main`, entrypoint `MiniProject/dashboard/app.py`, Python 3.11 บน Streamlit Community Cloud มี requirements ข้าง entrypoint อ้างอิงไฟล์หลักและ SQLite snapshot แนบ CSV; แอปอ่านอย่างเดียว ไม่ต้อง ETL เมื่อเปิดเว็บ

สถานะการเผยแพร่จริงและข้อมูลสมาชิกที่ยังต้องยืนยันระบุใน [README](README.md) ไม่ถือว่า deploy สำเร็จจนกว่าจะมี URL ที่เปิดทดสอบได้
