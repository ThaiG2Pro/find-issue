---
name: nextjs-figma-visual-qa
description: >
  Verify UI đã implement trên CMS có khớp với Figma design không.
  Dùng Figma MCP để lấy lại screenshot gốc, so sánh với UI thực tế theo checklist,
  report PASS/FAIL với danh sách điểm lệch cụ thể.
  Dùng ở S5 QA sau khi developer hoàn thành CMS UI task.
tags: [qa, nextjs, figma]
---

# Figma Visual QA

Verify UI đã implement khớp Figma design. Chạy sau S4 Build, trước khi close task CMS UI.

## Khi nào dùng skill này

- S5 QA: sau khi developer hoàn thành task có CMS UI
- Requirements.md hoặc design.md có Figma URL
- Cần confirm UI đã đúng trước khi merge

## Input cần có

- Figma URL của màn hình cần verify (từ requirements.md hoặc design.md)
- File path của component/page đã implement
- Dev server đang chạy (hoặc screenshot thực tế từ browser)

## Step 1: Lấy Figma ground truth

Từ Figma URL, extract fileKey và nodeId rồi gọi:

```
get_screenshot(fileKey, nodeId)       → ảnh design gốc làm ground truth
get_design_context(fileKey, nodeId)   → spec chi tiết: spacing, colors, typography
```

Nếu có nhiều màn hình → lấy từng màn hình riêng.

## Step 2: Đọc code đã implement

Đọc file component/page tương ứng để hiểu những gì đã được implement:
- Layout structure
- Colors và typography đang dùng
- Spacing values
- Component nào được dùng

## Step 3: So sánh theo checklist

Đối chiếu code với Figma screenshot + design context:

### Layout & Spacing
- [ ] Số columns và grid layout khớp
- [ ] Spacing giữa các elements khớp (dùng MUI spacing scale hay Tailwind gap)
- [ ] Padding trong card/section khớp
- [ ] Alignment (left/center/right) khớp

### Typography
- [ ] Font size đúng variant MUI (h4/h5/body1/body2/caption)
- [ ] Font weight đúng (regular/medium/semibold/bold)
- [ ] Không hardcode fontFamily — dùng MUI theme
- [ ] Line height và letter spacing hợp lý

### Colors
- [ ] Không còn hardcode hex — dùng MUI tokens
- [ ] Primary color đúng (`color='primary'`)
- [ ] Text colors đúng (`text.primary` / `text.secondary` / `text.disabled`)
- [ ] Background đúng (`background.paper` / `background.default`)
- [ ] Error/success/warning dùng đúng semantic color

### Components
- [ ] Đúng MUI component (Card, Button, TextField, Chip...)
- [ ] Button variant đúng (contained/outlined/text)
- [ ] Icons đúng tên tabler-*
- [ ] CustomAvatar dùng đúng skin/color/size

### Interactive States
- [ ] Hover state hiển thị đúng
- [ ] Disabled state đúng
- [ ] Loading state có spinner/skeleton
- [ ] Empty state có message

### Responsive
- [ ] Không vỡ layout ở md breakpoint (900px)
- [ ] Không dùng hardcode px cho padding/margin lớn

### Vuexy Conventions
- [ ] Layout dùng Tailwind className, không dùng sx cho flex/gap
- [ ] Logical spacing đúng (mbe-, pbe-, is-full...)
- [ ] `'use client'` chỉ khi thực sự cần
- [ ] ApexCharts dùng dynamic() import

## Step 4: Report kết quả

### Format report

```markdown
## Figma Visual QA Report

**Screen**: [Tên màn hình]
**Figma**: [URL]
**Component**: [file path]
**Result**: PASS ✅ / FAIL ❌ / PARTIAL ⚠️

### Issues Found (nếu có)

| Severity | Element | Figma | Implemented | Fix |
|----------|---------|-------|-------------|-----|
| HIGH | Button primary | `variant=contained color=primary` | hardcode `#00b3ff` | Dùng `color='primary'` |
| MEDIUM | Card spacing | `p: 24px` | `p: 3` ✅ | — |
| LOW | Icon size | `text-[22px]` | `text-xl` | Dùng `text-[22px]` |

### Checklist Summary
- Layout: ✅ / ❌
- Typography: ✅ / ❌
- Colors: ✅ / ❌
- Components: ✅ / ❌
- States: ✅ / ❌
- Responsive: ✅ / ❌
- Vuexy Conventions: ✅ / ❌
```

### Severity levels

- **HIGH**: Sai màu, sai layout cơ bản, hardcode hex — user nhìn thấy ngay
- **MEDIUM**: Spacing lệch nhỏ, font weight sai — cần fix trước merge
- **LOW**: Minor pixel diff, có thể accept nếu không ảnh hưởng UX

### Kết quả

- **PASS**: Không có HIGH issue, MEDIUM ≤ 2
- **PARTIAL**: Có MEDIUM issues — cần fix trước merge, không block nếu có plan
- **FAIL**: Có bất kỳ HIGH issue nào — phải fix trước khi close task

## Step 5: Xử lý sau report

### Nếu PASS
- Ghi vào task comment: `figma-visual-qa: PASS ✅`
- Proceed to S5 QA gate

### Nếu PARTIAL hoặc FAIL
- List cụ thể từng issue với fix suggestion
- Developer fix theo list
- Chạy lại verify sau khi fix
- Không close task cho đến khi PASS

## Lưu ý

- Không cần pixel-perfect 100% — Vuexy theme có thể render hơi khác Figma
- Focus vào semantic correctness: đúng màu token, đúng component, đúng layout
- Nếu Figma dùng custom component không có trong Vuexy → chấp nhận MUI equivalent gần nhất
- Dark mode: verify ở light mode là đủ trừ khi spec yêu cầu dark mode
