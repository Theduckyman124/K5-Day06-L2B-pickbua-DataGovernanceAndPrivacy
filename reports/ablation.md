# Self-evaluation & ablation trên split dev — T02

| Mục | Giá trị |
|---|---|
| Dữ liệu | 56 ảnh `dev` · nhãn `reports/gold_set_dev.csv` (28 lỗi / 28 sạch, xem `reports/gold_set_protocol.md`) |
| Budget | B = 28 (50% số ảnh, cùng tỉ lệ với eval: 20/40) |
| Commit | PoC đóng băng `ba5b2c2` · seed 42 · offline |
| Lệnh | `python -m tools.t02_self_eval --pred out/<run>/ranked_review.csv --run-name <run> --out reports/selfeval_dev_<run>.json` · `python -m tools.t02_ablation --out-json reports/ablation_dev.json` |
| Số liệu gốc | `reports/selfeval_dev_random.json`, `reports/selfeval_dev_baseline.json`, `reports/selfeval_dev_poc.json`, `reports/ablation_dev.json` |

> Đây là **tự đánh giá trên dev bằng nhãn nhóm tự gán**, không phải metric chính thức (Defect Recall@20 trên `eval`,
> do giảng viên chấm bằng GT ẩn). Split `eval` không được chấm ở đây. Nhãn dev được gán sau khi tham số đã đóng băng,
> nên các số dưới đây không được dùng để chỉnh lại tham số.

## 1. Baseline vs PoC (dev, B = 28)

| Run | Defect Recall@28 | Wilson 95% CI | Ảnh gắn RECAPTURE | Ảnh sạch bị gắn RECAPTURE | Đúng loại lỗi (trên ảnh lỗi) |
|---|---|---|---|---|---|
| Random (`src.examples.random_baseline`, seed 42) | 0.500 (14/28) | 0.326–0.674 | — | — | — |
| Baseline Laplacian (`src.baseline_t02`, ngưỡng quantile 0.25 trên dev = 222.3) | 0.821 (23/28) | 0.644–0.921 | 14 | 3 (cả 3 là cam_B) | 0.286 |
| **PoC sigmoid** (`src.pipeline`) | **0.893 (25/28)** | 0.728–0.963 | 26 | 2 (dusk) | 0.857 |

Vì dev có đúng 28 ảnh lỗi và B = 28, Precision@28 = Recall@28 ở cả ba run.

### Theo slice (tỉ lệ ảnh lỗi nằm trong top-28 · tỉ lệ ảnh sạch lọt vào top-28)

| Slice | N | Baseline recall | PoC recall | Baseline false alarm | PoC false alarm |
|---|---|---|---|---|---|
| light = day | 36 | 0.778 | 0.833 | 0.167 | 0.056 |
| light = dusk | 16 | 0.875 | 1.000 | 0.125 | 0.250 |
| light = night | 4 | 1.000 | 1.000 | 0.500 | 0.000 |
| camera = cam_A | 36 | 0.722 | 0.833 | 0.000 | 0.111 |
| camera = cam_B | 20 | 1.000 | 1.000 | 0.500 | 0.100 |
| defect = blur | 8 | 1.000 | 1.000 | | |
| defect = compression | 10 | 0.800 | 1.000 | | |
| defect = dark | 6 | 1.000 | 0.500 | | |
| defect = glare | 4 | 0.250 | 1.000 | | |

- Ba failure mode của baseline được thấy rõ trên dev: **lóa cục bộ** bị bỏ sót (glare 1/4), **cam_B** bị báo nhầm
  (3 ảnh cam_B sạch bị gắn RECAPTURE, false alarm cam_B 0.5), và ảnh **night** sạch lọt top-28 (0.5, N = 2).
  PoC cải thiện cả ba trên dev: glare 4/4; ảnh cam_B sạch bị gắn RECAPTURE giảm 3 → 1 (ảnh còn lại, `img_12_0`, bị báo
  compression chứ không phải do độ mềm — failure case 2); night false alarm 0.
- PoC **kém hơn baseline ở `dark`** (3/6 so với 6/6): bốn ảnh ban ngày bị thiếu sáng vừa phải bị PoC coi là sạch
  (failure case 1 trong `reports/failure_cases.md`).
- PoC báo nhầm hai ảnh hoàng hôn sạch là `compression` (failure case 2), làm false alarm dusk tăng (0.125 → 0.250).
- Khoảng tin cậy rộng (N = 28 ảnh lỗi): chênh lệch Baseline 0.821 và PoC 0.893 nằm trong khoảng chồng lấn,
  nên chưa đủ để khẳng định PoC tốt hơn có ý nghĩa thống kê; chênh lệch so với random (0.500) thì rõ ràng.

## 2. Ablation (dev, B = 28)

Mỗi biến thể xuất phát từ tham số đã đóng băng và tắt một thành phần bằng cách ghi đè tham số tương ứng
(`tools/t02_ablation.py`); thuật toán và các tham số khác giữ nguyên.

| Biến thể | Recall@28 | Ảnh gắn RECAPTURE | Ảnh sạch bị gắn | Recall blur | Recall dark | Recall glare | Recall compression | FA top-28 night | FA top-28 cam_B |
|---|---|---|---|---|---|---|---|---|---|
| PoC đầy đủ | 0.893 (25/28) | 26 | 2 | 1.000 | 0.500 | 1.000 | 1.000 | 0.0 | 0.1 |
| bỏ nhánh blur | 0.750 (21/28) | 18 | 2 | 0.125 | 1.000 | 1.000 | 1.000 | 1.0 | 0.4 |
| bỏ nhánh dark | 0.893 (25/28) | 25 | 2 | 1.000 | 0.500 | 1.000 | 1.000 | 0.0 | 0.1 |
| bỏ nhánh glare | 0.893 (25/28) | 23 | 2 | 1.000 | 1.000 | 0.250 | 1.000 | 0.0 | 0.1 |
| bỏ nhánh compression | 0.857 (24/28) | 14 | 0 | 1.000 | 1.000 | 1.000 | 0.600 | 1.0 | 0.3 |
| bỏ ngưỡng blur theo camera | 0.893 (25/28) | 26 | 2 | 1.000 | 0.500 | 1.000 | 1.000 | 0.0 | 0.1 |
| bỏ ngưỡng glare riêng cho đêm | 0.893 (25/28) | 26 | 2 | 1.000 | 0.500 | 1.000 | 1.000 | 0.0 | 0.1 |

Nhận xét:

1. **Nhánh blur đóng góp nhiều nhất**: bỏ đi thì Recall@28 giảm 0.893 → 0.750, blur chỉ còn 1/8, đồng thời ảnh night
   và cam_B sạch lọt top-28 nhiều hơn (night 0 → 1.0, cam_B 0.1 → 0.4).
2. **Nhánh compression** là nguồn của cả hai false alarm: bỏ đi thì không còn ảnh sạch bị gắn RECAPTURE, nhưng recall
   compression giảm 1.0 → 0.6 và Recall@28 giảm 0.893 → 0.857.
3. **Nhánh glare** cần cho lóa cục bộ (glare 1.0 → 0.25 khi bỏ). Recall@28 tổng không đổi vì chỗ trống trong top-28
   được lấp bởi ảnh `dark`; recall tổng che mất thay đổi theo loại lỗi, nên cần đọc kèm cột theo loại lỗi.
4. **Nhánh dark gần như không đóng góp** ở ngưỡng đã đóng băng (bỏ đi không đổi recall); đây là hệ quả của
   failure case 1 (ảnh ngày thiếu sáng bị nhận là ảnh đêm).
5. **Ngưỡng blur theo camera và ngưỡng glare riêng cho đêm không tạo khác biệt trên dev**: không ảnh dev nào nằm gần
   các ngưỡng này. Dev không đủ dữ liệu để kết luận hai thành phần này có ích; giữ nguyên vì đã đóng băng.

## 3. Giới hạn

- Nhãn gold do một người duyệt (nhãn sơ bộ do AI đề xuất), chưa có đồng thuận độc lập — xem `reports/gold_set_protocol.md` §4.
- N nhỏ (56 ảnh, night chỉ 4) → khoảng tin cậy rộng; không suy rộng kết quả slice night.
- `score` của PoC bị chặn ở 0.98 (6 ảnh dev trùng 0.98), thứ tự trong nhóm trùng điểm theo thứ tự sắp xếp của pipeline.
- Không có số trên `eval`; kết quả chính thức do giảng viên chấm.
