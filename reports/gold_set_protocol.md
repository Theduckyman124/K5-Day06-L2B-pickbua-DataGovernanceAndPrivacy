# Gold set protocol — T02 · Raw QC Triage (split dev)

| Mục | Giá trị |
|---|---|
| File nhãn | `reports/gold_set_dev.csv` (56 dòng) |
| Phạm vi | **chỉ split `dev`**: 56 ảnh, 14 cảnh gốc × 4 ảnh (`img_XX_0..3`); không gán nhãn ảnh `eval` |
| Mục đích | tự đánh giá trên dev (`tools/t02_self_eval.py`) và ablation (`tools/t02_ablation.py`); không thay cho đánh giá chính thức bằng GT ẩn của giảng viên |
| Ngày | 2026-11-15, sau commit freeze `ba5b2c2` |
| Người gán | nhãn sơ bộ do trợ lý AI (Claude) đề xuất khi xem từng ảnh; Duong Manh Huy (M5) duyệt từng ảnh và chịu trách nhiệm nhãn cuối |
| Kết quả duyệt | 56/56 ảnh đã duyệt trên trang so sánh từng cặp (ảnh mốc `_0` · ảnh cần gán · nhãn đề xuất); 0 nhãn bị sửa; 2 ca được xem lại và giữ nhãn (§3) |

## 1. Nhãn

| Cột | Giá trị |
|---|---|
| `defect_type` | `none` · `blur` · `dark` · `glare` · `compression` (một nhãn chính cho mỗi ảnh) |
| `is_defect` | 1 nếu `defect_type ≠ none`, ngược lại 0 |
| `severity` | 0 = không lỗi · 1 = lỗi nhẹ (vật thể và biển số vẫn nhận ra được) · 2 = lỗi rõ (mất chi tiết vật thể hoặc biển số) |
| `note` | bằng chứng nhìn thấy, cùng cách ghi với `reports/review_policy.md` §2.3 |

Định nghĩa từng nhãn dùng đúng bảng `reports/review_policy.md` §2.2, để nhãn gold và quyết định review thống nhất:

| Nhãn | Là lỗi khi | Không phải lỗi khi |
|---|---|---|
| `blur` | cạnh nhoè rõ so với ảnh cùng cảnh | cam_B mềm đều toàn ảnh (đặc tính quang học) |
| `dark` | tối hơn rõ so với ảnh gốc **cùng điều kiện `light`**, mất chi tiết vật thể | ảnh đêm tối tự nhiên, vẫn thấy xe, biển số, vạch đường |
| `glare` | vùng cháy trắng che vật thể, kể cả vùng nhỏ chỉ che biển số | đèn sáng không che vật thể |
| `compression` | khối 8×8, viền răng cưa, dải màu thấy rõ | nhiễu hạt nhẹ của ảnh đêm |

## 2. Cách gán

1. Mỗi cảnh: xem `img_XX_0` trước làm mốc (độ nét, độ sáng, màu bình thường của cảnh đó), sau đó lần lượt `img_XX_1..3`.
2. So sánh với mốc theo bảng trên; ảnh không kém mốc → `none`.
3. Không xem output của pipeline (`ranked_review.csv`, `score`) trong lúc gán nhãn.
4. Ảnh có nhiều lỗi: chọn lỗi làm mất thông tin nhiều nhất (thường là lỗi che biển số).
5. Người duyệt mở từng cặp ảnh (mốc và ảnh cần gán) và xác nhận hoặc sửa nhãn.

## 3. Kết quả

| | Số ảnh |
|---|---|
| Tổng | 56 |
| `none` | 28 (14 ảnh `_0` mốc + 14 ảnh `_1` không lỗi) |
| `compression` | 10 |
| `blur` | 8 |
| `dark` | 6 |
| `glare` | 4 |
| Lỗi nhẹ (`severity = 1`) | 6 (`img_08_2`, `img_08_3`, `img_09_3`, `img_10_3`, `img_12_2`, `img_20_2`) |

Theo slice: `light` day 18 lỗi / 18 sạch · dusk 8 / 8 · night 2 / 2; `camera_id` cam_A 18 / 18 · cam_B 10 / 10.

### Ca được xem lại khi duyệt: ảnh mốc cam_B mềm hơn ảnh `_1`

Khi duyệt, người duyệt nhận thấy ở `img_09_1` và `img_12_1` ảnh mốc `_0` mờ hơn ảnh cần gán. Đo độ nét Laplacian
(`src.common.image_ops.laplacian_variance`) xác nhận đây là quy luật của cả 4 cảnh cam_B trong dev:

| Cảnh | Camera | Laplacian `_0` | Laplacian `_1` |
|---|---|---|---|
| `img_00` | cam_B | 267 | 1366 |
| `img_09` | cam_B | 187 | 876 |
| `img_12` | cam_B | 166 | 877 |
| `img_21` | cam_B | 221 | 1081 |
| `img_02` (đối chứng) | cam_A | 1114 | 1129 |
| `img_07` (đối chứng) | cam_A | 868 | 880 |

Ảnh `_0` của cam_B mềm đều toàn ảnh, không nhoè cục bộ, nên giữ nhãn `none` theo §1 (độ mềm quang học cam_B không
phải lỗi); ảnh `_1` nét hơn cũng là `none`. Đây chính là nhóm ảnh baseline Laplacian báo nhầm
(`img_09_0`, `img_12_0`, `img_21_0` — `reports/ablation.md` §1).

## 4. Giới hạn

- Một người duyệt cuối, không có người gán độc lập thứ hai → **chưa đo được độ đồng thuận (kappa)**. Các ca ranh giới
  (lỗi nhẹ ở §3) là nơi nhãn dễ khác nhau nhất.
- Nhãn sơ bộ do AI đề xuất có thể mang thiên lệch của mô hình; vì vậy mọi nhãn được người duyệt xác nhận trên ảnh gốc.
- Chỉ 4 ảnh night trong dev (2 lỗi) → kết quả slice night trên dev có độ bất định rất lớn.
- Bộ nhãn được tạo **sau** khi tham số đã đóng băng: chỉ dùng để mô tả hiệu năng trên dev và phân tích lỗi,
  không dùng để chỉnh lại tham số.
