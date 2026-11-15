# Group Report — Day 06 Data Lab (Field-to-Release PoC)

## 00 · Header

| Mục                      | Giá trị                                                                                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Group ID                 | pickbua                                                                                                                                                                              |
| Challenge                | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng                                                                                                                                       |
| Thành viên (5) + vai trò | 1. Nguyễn Thái Đức (Lead/Integrator) · 2. Phạm Đức Việt (Data & fixtures) · 3. Vũ Hưng (Core algorithm) · 4. Nguyễn Hữu Đăng (QA/metric) · 5. Dương Mạnh Huy (Human review + report) |
| Git URL                  | https://github.com/Theduckyman124/K5-Day06-L2B-pickbua-DataGovernanceAndPrivacy                                                                                                      |
| Tag `demo-180m` (commit) | `84e903a`                                                                                                                                                                            |
| Tag `final-24h` (commit) | commit cuối trên `main` mang tag `final-24h` (`git rev-parse final-24h`)                                                                                                             |
| Deadline (giờ VN)        | mốc +24h sau buổi lab (bản nộp = tag `final-24h`)                                                                                                                                    |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?**
  - Đội huấn luyện mô hình: ảnh mờ, tối, lóa hoặc nén nặng lọt vào tập huấn luyện khiến nhãn khó chính xác và mô hình
    học sai, đặc biệt với vật thể nhỏ như biển số.
  - Đội thu thập dữ liệu: báo nhầm (false alarm) dẫn đến chụp lại những ảnh vốn dùng được, tốn chi phí và thời gian;
    bỏ sót (miss) làm lỗi chỉ lộ ra ở giai đoạn gán nhãn hoặc huấn luyện.
  - Người review: chỉ có thời gian xem 20 ảnh; nếu thứ tự xếp hạng sai, công sức review rơi vào ảnh sạch.
- **Điểm nghẽn cụ thể:** không thể kiểm tra thủ công toàn bộ ảnh; một ngưỡng độ nét toàn ảnh (baseline) báo nhầm ảnh
  từ camera quang học mềm (cam_B) và ảnh đêm, đồng thời bỏ sót vùng lóa nhỏ trên ảnh vẫn nét.
- **Đầu vào → đầu ra:** 96 ảnh 320×180 (synthetic, CC0) kèm `images.csv` (`camera_id`, `light`, `split`) và `manifest.csv`
  (sha256) → `ranked_review.csv` (mỗi ảnh có `score`, `pred_defect_type`, `pred_action`) → top-20 cho người review
  → `audit_log.jsonl` và quyết định batch `GO / HOLD / REWORK` (`decision.json`, kèm `reason_code` và `owner`).
- **Tiêu chí GO / HOLD / REWORK** (chốt trước khi đánh giá, chi tiết tại `reports/review_policy.md` §3): khi hơn 20% ảnh
  của batch cần chụp lại, batch ở trạng thái HOLD cho tới khi người review xác nhận top-20, sau đó chuyển REWORK; khi tỉ lệ
  này không vượt 20%, batch GO kèm danh sách ảnh cần chụp lại riêng lẻ.
- **Giả định của nhóm (cần domain owner / DPO / legal xác nhận):**
  1. Ảnh đêm tối tự nhiên mà vẫn thấy rõ vật thể được coi là dùng được (`none`); ảnh tối hơn rõ so với ảnh cùng điều
     kiện ánh sáng là lỗi `dark`.
  2. Vùng lóa che vật thể, kể cả vùng nhỏ chỉ che biển số, được coi là lỗi (`glare`) dù phần còn lại của ảnh nét.
  3. Độ mềm quang học đồng đều của cam_B không phải lỗi `blur`.
  4. Ngưỡng 20% ảnh cần chụp lại cho cả batch là chính sách vận hành, không phải giá trị tối ưu từ dữ liệu.
  5. Dữ liệu là synthetic, không chứa người hay biển số thật; áp dụng cho dữ liệu thật cần đánh giá lại quyền riêng tư
     và license. Nhóm không tuyên bố đạt GDPR hay luật Việt Nam.

## 02 · Data & provenance

| Split          | N                        | Nguồn / link                                                                                        | License | Synthetic? |
| -------------- | ------------------------ | --------------------------------------------------------------------------------------------------- | ------- | ---------- |
| dev            | 56 ảnh (14 cảnh gốc × 4) | `fixtures/t02_raw_qc/` — `synthetic:tools/make_fixtures.py (seed 42)` (generator ở repo giảng viên) | CC0-1.0 | có         |
| eval / heldout | 40 ảnh (10 cảnh gốc × 4) | như trên                                                                                            | CC0-1.0 | có         |

- **Schema & class mapping:** `images.csv` = `image_id, path, camera_id ∈ {cam_A, cam_B}, light ∈ {day, dusk, night}, split`.
  Nhãn lỗi: `none · blur · dark · glare · compression` (+ `severity` 0–2) → hành động `KEEP` (none) / `RECAPTURE` (còn lại).
- **Seed:** 42 · **Cách chia split:** theo cảnh gốc (`group_id = img_XX`): bốn ảnh của một cảnh luôn cùng split, tránh rò rỉ
  giữa dev và eval.
- **`manifest.csv` verified (sha256):** có — `python -m tools.verify_manifests` → `14 manifests, 0 failing`; pipeline kiểm
  lại ở bước `load()` với `strict_provenance: true`. File `.gitattributes` (`fixtures/** -text`) giữ nguyên byte của fixture
  khi clone trên Windows (đã kiểm với `core.autocrlf=true`: `preflight` 0 FAIL).
- **Dữ liệu thật:** pipeline không dùng dữ liệu thật. Gold set để tự đánh giá là nhãn nhóm tự gán cho 56 ảnh dev
  (`reports/gold_set_dev.csv`, protocol `reports/gold_set_protocol.md`): 28 lỗi / 28 sạch (compression 10, blur 8, dark 6,
  glare 4), nhãn sơ bộ do trợ lý AI đề xuất và M5 duyệt 56/56. Không gán nhãn ảnh eval.

## 03 · Research & design

- **References và lý do chọn kỹ thuật** (chi tiết ở §11):
  - Variance of Laplacian (Pech-Pacheco et al., 2000) là độ đo độ nét kinh điển → dùng làm **baseline** đúng yêu cầu đề;
    nó phụ thuộc nội dung và quang học nên một ngưỡng toàn cục báo nhầm cam_B — chính là failure mode cần khắc phục.
  - Blind blocking measurement (Wang, Bovik & Evans, 2000): đo cường độ "tín hiệu khối" tại biên 8×8 mà không cần ảnh gốc
    → nhánh **compression** dùng tỉ lệ chênh lệch tại biên khối so với chênh lệch trung bình.
  - ACDC (Sakaridis et al., ICCV 2021): ảnh điều kiện bất lợi (đêm, sương, mưa) là dữ liệu hợp lệ và cần đánh giá theo
    **điều kiện** → ngưỡng dark/glare phụ thuộc ngữ cảnh đêm thay vì một ngưỡng độ sáng chung.

- **Data flow:**

  ```
  images.csv + manifest.csv ──load (sha256)──► process: 4 xác suất lỗi (sigmoid)
     blur  : gradient variance, ngưỡng theo camera_id
     dark  : độ sáng / tỉ lệ pixel tối, công thức riêng cho ảnh đêm
     glare : tỉ lệ pixel bão hoà, ngưỡng riêng cho ảnh đêm
     compression : blockiness 8×8
  ──► score = xác suất lỗi lớn nhất (≥ 0.25 → RECAPTURE)
  ──rank──► top-20 → review_queue.csv + contact_sheet.html
  ──review──► review_queue_reviewed.csv → override pred_action → audit_log.jsonl
  ──decide──► decision.json / decision_log.csv (GO / HOLD / REWORK + reason_code + owner)
  ```

- **Thành phần offline:** không dùng model pretrained hay weights; chỉ numpy, pandas, Pillow (phiên bản ở §08). Toàn bộ
  tham số đóng băng trong `configs/lab.yaml` (`params:`, commit `ba5b2c2`).
- **Trade-offs đã cân nhắc:**
  - Ngưỡng thủ công + sigmoid thay vì mô hình học: không có GT để huấn luyện, N nhỏ; đổi lại phải chấp nhận ngưỡng chưa tối ưu.
  - `flag_threshold = 0.25` (thấp hơn điểm giữa sigmoid) ưu tiên không bỏ sót hơn là ít báo nhầm; hệ quả là 46/96 ảnh
    (47.9%) bị gắn RECAPTURE và hai ảnh hoàng hôn sạch bị báo compression (§06).
  - `score` bị chặn ở 0.98 để tránh "chắc chắn tuyệt đối", đổi lại tạo nhóm điểm trùng ở đầu bảng xếp hạng.
  - Tự nhận ảnh đêm từ độ sáng giúp chạy được với thư mục ảnh không có metadata, nhưng ghi đè `light = day` của ảnh
    ngày thiếu sáng (failure case 1).

## 04 · Baseline vs PoC

- **Baseline:** một ngưỡng variance of Laplacian toàn ảnh (`src/baseline_t02.py`, commit `e44ff01`); ngưỡng = quantile 0.25
  của 56 ảnh dev = 222.3; `score = 1 / (1 + lap_var)`; ảnh dưới ngưỡng → `blur / RECAPTURE`.
- **PoC:** `src/pipeline.py` — bốn xác suất lỗi dạng sigmoid (thuật toán `53726b5`), tham số đóng băng trong
  `configs/lab.yaml` (commit `ba5b2c2`), review + quyết định batch theo `reports/review_policy.md`.
- **Cùng budget / cùng heldout / cùng seed:** xác nhận — cùng pool 96 ảnh, cùng `images.csv`, B = 20 cho queue, seed 42,
  `--offline`; trên dev cả hai được chấm bằng cùng gold set, cùng B = 28.

**Bảng 1 · Baseline vs PoC & hard slices.** `python -m src.evaluate` cần `fixtures/t02_raw_qc/gt/labels.csv` của giảng viên;
trong repo học viên lệnh dừng với exit 2 (`ground truth file not found`), nên nhóm **không có** `reports/metrics_*.json`
chính thức. Bảng dưới là **tự đánh giá trên dev** (`tools/t02_self_eval.py`, nhãn `reports/gold_set_dev.csv`), không phải
metric chính thức trên eval.

| Metric (unit)                                     | Baseline                        | PoC                             | Δ & chú thích                                                                                                                 |
| ------------------------------------------------- | ------------------------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Primary (dev self-eval): Defect Recall@28 (tỉ lệ) | 0.821 (23/28) · CI 0.644–0.921  | 0.893 (25/28) · CI 0.728–0.963  | +0.071; higher = better; CI chồng lấn → chưa có ý nghĩa thống kê. Random: 0.500                                               |
| Hard-slice glare: recall trong top-28             | 0.250 (1/4)                     | 1.000 (4/4)                     | +0.750; N = 4 ảnh glare                                                                                                       |
| Hard-slice cam_B: ảnh sạch bị gắn RECAPTURE       | 3/10                            | 1/10                            | −2; lower = better; N = 10 ảnh cam_B sạch; ảnh còn lại (`img_12_0`) bị báo compression, không phải do độ mềm (failure case 2) |
| Hard-slice night: false alarm trong top-28        | 0.500 (1/2)                     | 0.000 (0/2)                     | −0.5; N = 2 (rất nhỏ)                                                                                                         |
| Hard-slice dark: recall trong top-28              | 1.000 (6/6)                     | 0.500 (3/6)                     | −0.5; PoC kém hơn — failure case 1                                                                                            |
| Review@B: Precision@28 (dev) / FP                 | 0.821 / 5 ảnh sạch trong top-28 | 0.893 / 3 ảnh sạch trong top-28 | B = 28 trên dev; queue thật B = 20 trên 96 ảnh                                                                                |
| Runtime / 100 items                               | 0.258 s                         | 0.265 s                         | từ `run_info.json` (96 ảnh: 0.248 s / 0.255 s); CPU = AMD64 Family 25 Model 117, Windows 11                                   |

## 05 · Evaluation protocol

- **Công thức primary metric** (`reports/metric_contract.md`, `src/metrics/tracks.py::eval_t02`): Defect Recall@B =
  số ảnh lỗi thật trong top-B / số ảnh lỗi thật, tính trên split **eval**, đơn vị là ảnh; top-B lấy theo `score` giảm dần
  (`mergesort`). TP = ảnh lỗi nằm trong top-B, FN = ảnh lỗi ngoài top-B, FP = ảnh sạch trong top-B. Kèm Precision@B.
- **Threshold / budget:** B = 20 trên eval (40 ảnh) — chốt 2026-11-14 21:05 trong metric contract. Tham số PoC đóng băng
  2026-11-15 (commit `ba5b2c2`) trước khi review và trước mọi đánh giá; gold set dev được gán sau freeze và không dùng để
  chỉnh tham số. Tự đánh giá trên dev dùng B = 28 (50% số ảnh, cùng tỉ lệ 20/40 của eval).
- **Độ bất định:** Wilson 95% CI cho mọi tỉ lệ (N nhỏ): dev N = 56 (28 lỗi), slice night chỉ 4 ảnh → không suy rộng.
- **Lệnh evaluate chính xác** (giảng viên chạy khi có `gt/`):
  `python -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json`
  (tương tự với `out/baseline/ranked_review.csv` → `reports/metrics_baseline.json`, sau đó `python -m src.compare ...`).
  Tự đánh giá trên dev: `python -m tools.t02_self_eval --pred out/poc/ranked_review.csv --run-name poc --out reports/selfeval_dev_poc.json`.

## 06 · Result slices

Dev self-eval, B = 28 (`reports/selfeval_dev_baseline.json`, `reports/selfeval_dev_poc.json`): recall trong top-28 /
tỉ lệ ảnh sạch lọt top-28.

| Slice          | N   | Baseline      | PoC           | Ghi chú                                                |
| -------------- | --- | ------------- | ------------- | ------------------------------------------------------ |
| light = day    | 36  | 0.778 / 0.167 | 0.833 / 0.056 | PoC bỏ sót ảnh ngày thiếu sáng (failure case 1)        |
| light = dusk   | 16  | 0.875 / 0.125 | 1.000 / 0.250 | PoC báo nhầm 2 ảnh hoàng hôn sạch (failure case 2)     |
| light = night  | 4   | 1.000 / 0.500 | 1.000 / 0.000 | N rất nhỏ                                              |
| camera = cam_A | 36  | 0.722 / 0.000 | 0.833 / 0.111 |                                                        |
| camera = cam_B | 20  | 1.000 / 0.500 | 1.000 / 0.100 | baseline báo nhầm 3/4 ảnh mốc cam_B (mềm do quang học) |
| defect = glare | 4   | 0.250         | 1.000         | lóa cục bộ trên ảnh vẫn nét                            |
| defect = dark  | 6   | 1.000         | 0.500         |                                                        |

Ablation trên dev (`reports/ablation.md`): bỏ nhánh blur → Recall@28 0.893 → 0.750; bỏ nhánh compression → hết false alarm
nhưng recall compression 1.0 → 0.6; ngưỡng blur theo camera và ngưỡng glare riêng cho đêm không tạo khác biệt trên dev.

- **Failure case 1** (`reports/failure_cases.md`, `demo/failure_case_1.png`): `img_02_3`, `img_07_2`, `img_10_3`, `img_20_2`
  — ảnh ban ngày thiếu sáng (mean ≈ 24, `dark_frac` ≈ 0.7) bị chấm sạch. Root cause: điều kiện tự nhận đêm
  (`dark_frac > 0.60` và `mean < 35`) ghi đè `light = day`, nên ảnh bị so với mốc độ sáng của ảnh đêm (14).
- **Failure case 2** (`demo/failure_case_2.png`): `img_22_0`, `img_12_0` — ảnh hoàng hôn sạch bị gắn `compression / RECAPTURE`
  (xác suất 0.38 / 0.33). Root cause: trời chuyển màu đẩy blockiness lên 1.51–1.55, sát tâm sigmoid 1.65, và
  `flag_threshold = 0.25` thấp hơn điểm giữa sigmoid.
- **Latency / compute:** 96 ảnh trong 0.255 s (≈ 2.7 ms/ảnh) cho PoC, 0.248 s cho baseline; CPU AMD64 Family 25 Model 117,
  Windows 11, Python 3.14.10; không dùng GPU.

## 07 · Human & decision

- **Review queue:** `out/poc/review_queue.csv` — top-B = 20 trên 96 ảnh theo `score` giảm dần; thẻ hiển thị `reason`,
  `suggested_action`, `slice` và ảnh trong `out/poc/contact_sheet.html` (offline, nút Export CSV).
- **Cách override + audit log** (`reports/review_policy.md` §2): `approve` giữ đề xuất; `reject` (`override_value = KEEP`) và
  `edit` (`KEEP`/`RECAPTURE`) ghi đè `pred_action` qua `apply_overrides` và ghi `out/poc/audit_log.jsonl`
  (`actor, action, item_id, before, after, reason`); `score` không bị đổi nên metric không bị ảnh hưởng. Dòng có quyết định
  mà thiếu `reviewer`, hoặc quyết định ngoài 5 giá trị hợp lệ → exit 2.
- **Kết quả review thật** (`reports/review_queue.csv`, `demo/review_contact_sheet.png`): reviewer Duong Manh Huy xem 20/20
  ảnh, so với ảnh gốc cùng cảnh, ghi note cho mỗi ảnh → 20 `approve`, 0 override (đồng thuận với pipeline 20/20, Wilson
  95% CI 0.839–1.000; đây là đánh giá của reviewer, không phải GT). Vì không có override nên không phát sinh
  `audit_log.jsonl`; đường override được kiểm bằng kịch bản T2/T6 (`reports/review_policy.md` §5) và
  `tests/test_t02_pipeline.py::test_t02_human_override_writes_audit_log`.
- **Decision policy + `reason_code` + owner:** `reports/decision_log.csv` ghi hai lần chạy — trước review
  `HOLD / HIGH_DEFECT_RATE_HOLD`, sau review `REWORK / RECAPTURE_REQUIRED` (46/96 = 47.9%); owner Nguyen Thai Duc (Lead),
  tách biệt với reviewer.
- **Khi nào HOLD/REWORK thay vì tự động release:** khi hơn 20% ảnh cần chụp lại, kết quả tự động không được dùng một mình:
  batch HOLD cho tới khi có người review, sau đó REWORK; batch không được công bố khi còn dòng `escalate`.

## 08 · Reproduce & tests

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt "pandas>=2.1,<3"
.venv\Scripts\python -m tools.preflight
.venv\Scripts\python -m src.main --config configs/lab.yaml --track t02 --output out/poc --run-name poc --offline --seed 42
.venv\Scripts\python -m src.main --config configs/lab.yaml --track t02 --pipeline src.baseline_t02 --output out/baseline --run-name baseline --offline --seed 42
.venv\Scripts\python -m tools.t02_self_eval --pred out/poc/ranked_review.csv --run-name poc --out reports/selfeval_dev_poc.json
.venv\Scripts\python -m tools.t02_ablation --out-json reports/ablation_dev.json
.venv\Scripts\python -m pytest -q
```

- `pandas<3`: trên máy Windows bật Smart App Control, DLL của pandas 3.x bị chặn; pandas 2.3.3 chạy bình thường.
- **Output của `pytest -q`:** `50 passed, 39 skipped` (các test cần GT tự skip). Clean clone của `main` tại `demo-180m`:
  `preflight: 0 FAIL, 2 WARN` (thiếu `data/real/` và `models_optional/`, đều tuỳ chọn), PoC và baseline exit 0, số
  self-eval và ablation tái tạo khớp với file đã commit.
- **Máy / CPU / OS / Python:** Windows 11 (10.0.26200), AMD64 Family 25 Model 117, Python 3.14.10, numpy 2.5.4, pandas 2.3.3,
  Pillow 13.0.0 · **git sha:** `demo-180m` = `84e903a`; bản nộp cuối = tag `final-24h`.

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** fixture là ảnh synthetic CC0, không có người hay biển số thật. Thư mục `data/my_images/`
  (ảnh dashcam thật có xe và biển số, kèm 2 ảnh chụp màn hình, commit `53726b5`) nằm trong repo nhưng không được pipeline
  dùng, chưa rõ nguồn và license — trái quy tắc 4 của đề. Cần gỡ khỏi repo (`git rm -r --cached data/my_images`, chuyển sang
  `data/real/` đã gitignore); ảnh vẫn còn trong lịch sử git, nếu repo công khai cần đánh giá việc xoá khỏi lịch sử.
- **Điều chưa biết:** chưa có kết quả trên eval (cần GT của giảng viên); gold set dev do một người duyệt, chưa đo đồng thuận;
  review chỉ phủ top-20 nên không đo được bỏ sót ngoài queue (26 ảnh RECAPTURE ngoài queue chưa có người xem).
- **False alarms:** PoC gắn RECAPTURE 47.9% ảnh, nên batch luôn REWORK; ngoài queue, báo nhầm tập trung ở ảnh hoàng hôn
  (compression). Nếu scale 10×: ~460 ảnh/960 bị đề xuất chụp lại, người review 20 ảnh không phủ nổi → cần giảm báo nhầm
  (failure case 2) hoặc tăng budget review theo tỉ lệ; thời gian xử lý ≈ 2.7 ms/ảnh nên không phải nút thắt.
- **Pháp lý:** nhóm không tuyên bố đạt GDPR hay luật Việt Nam; các giả định ở §01 (định nghĩa lỗi, ngưỡng 20%) cần domain
  owner xác nhận, việc dùng ảnh thật cần DPO/legal đánh giá quyền riêng tư và license.
- **Kế hoạch cải tiến** (chỉ áp dụng sau khi chốt lại protocol, kiểm trên dev):
  1. Chỉ tự nhận ảnh đêm khi thiếu metadata `light`; với ảnh có `light`, so độ sáng với mức bình thường của slice đó.
  2. Đo blockiness tương đối theo ánh sáng hoặc chỉ trên vùng có cạnh để bỏ báo nhầm ảnh hoàng hôn.
  3. Thêm người gán độc lập cho gold set dev để đo kappa; kiểm 10 ảnh out-of-domain (mốc +24h của đề).

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên                   | Git author/email                                                      | Module / vai trò                                                                                | Commit SHA / diff chứng minh                                                                                                                                                                                                                                                                                                                                                     | Trình bày? |
| -------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Member 1 · Nguyễn Thái Đức | Theduckyman124 <nguyenthaiduc01022004@gmail.com>                      | Lead / Integrator · `configs/lab.yaml`                                                          | `4a53031`, `2fe56eb` — chọn track T02 (`track`, `track_config`) và owner trong `configs/lab.yaml`                                                                                                                                                                                                                                                                                | —          |
| Member 2 · Phạm Đức Việt   | DucViet <ducvietytb19@gmail.com> · phamducviet <pdviet1909@gmail.com> | Data & fixtures · `src/pipeline.py` (`load`, `process`)                                         | `53726b5` — thuật toán sigmoid 4 loại lỗi trong `process()` và `load()` quét thư mục ảnh không có `images.csv`; `f8cee57` giải conflict; `47cf858` gộp PR #3                                                                                                                                                                                                                     | —          |
| Member 3 · Vũ Hưng         | Hưng Vũ / hungvu208 <hungdabc1234@gmail.com>                          | Core algorithm                                                                                  | `6002a57` — bản pipeline đầu tiên (`pipeline.py`, 287 dòng) kèm output chạy thử; `3cdc2b1`, `58b8c02` — trên nhánh `hungvu`, chưa gộp vào `main`                                                                                                                                                                                                                                 | —          |
| Member 4 · Nguyễn Hữu Đăng | huudang-de / HuuDang_47 <dang36390@gmail.com>                         | QA / metric · `reports/metric_contract.md`, `src/baseline_t02.py`, `tests/test_t02_pipeline.py` | `e44ff01` — metric contract, baseline Laplacian, nối dây PoC 5 bước, 3 unit test; `c5d9899` gộp PR #2                                                                                                                                                                                                                                                                            | —          |
| Member 5 · Dương Mạnh Huy  | Duong Manh Huy <manhhuy2104@gmail.com>                                | Human review + report · `review()`/`decide()`, `reports/review_policy.md`, review thật, report  | `40eb1ff`, `9a1ab1a` (dòng contributor) · `43b98f3` (review policy) · `52d750d` (sửa `review()` crash, `decide()` theo policy) · `229a28a`, `ba5b2c2` (`.gitattributes`, freeze tham số) · `4a3f75f` (review thật top-20 + decision log) · `868387c` (gold set dev) · `be1eca7` (self-eval + ablation) · `4b1e82a` (failure cases) · `84e903a` (slides) · các commit report cuối | có         |

Ghi chú:

## 11 · References

| URL                                                                                                                                                                                                                                            | Ngày xem   | 1–2 dòng ý nghĩa (không chép nguyên văn)                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| https://produccioncientifica.ugr.es/documentos/618fa3df4fa218568b4e1706 — Pech-Pacheco, Cristóbal, Chamorro-Martínez, Fernández-Valdivia, _Diatom autofocusing in brightfield microscopy: a comparative study_, ICPR 2000, vol. 3, pp. 314–317 | 2026-11-15 | So sánh các độ đo lấy nét; nguồn thường được trích cho độ đo dựa trên Laplacian → cơ sở cho baseline độ nét toàn ảnh.                                          |
| https://ece.uwaterloo.ca/~z70wang/publications/icip00.html — Wang, Bovik, Evans, _Blind measurement of blocking artifacts in images_, ICIP 2000, doi:10.1109/ICIP.2000.899622                                                                  | 2026-11-15 | Đo hiện tượng khối do nén không cần ảnh gốc, coi ảnh là ảnh sạch cộng tín hiệu khối → cơ sở cho nhánh compression.                                             |
| https://openaccess.thecvf.com/content/ICCV2021/html/Sakaridis_ACDC_The_Adverse_Conditions_Dataset_With_Correspondences_for_Semantic_Driving_ICCV_2021_paper.html — Sakaridis, Dai, Van Gool, ACDC, ICCV 2021                                   | 2026-11-15 | Bộ dữ liệu lái xe trong điều kiện bất lợi (đêm, sương, mưa, tuyết) ghép cặp với ảnh điều kiện thường → ảnh đêm là dữ liệu hợp lệ, cần đánh giá theo điều kiện. |
| `docs/tracks/T02.md`, `reports/metric_contract.md` (repo này)                                                                                                                                                                                  | 2026-11-14 | Đề bài, output contract, metric và failure mode bắt buộc; định nghĩa metric của nhóm.                                                                          |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README (§8); input mẫu không chứa PII thật (fixture synthetic; `data/my_images/` ghi ở §09).
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics (dev self-eval), ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
