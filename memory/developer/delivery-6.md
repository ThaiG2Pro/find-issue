## 2026-06-29 — delivery-6: temp file MUST be in target.parent, never system /tmp

`os.replace(tmp, target)` là atomic chỉ khi cả hai nằm trên cùng filesystem.
`tempfile.mkstemp()` mặc định dùng system temp dir (`/tmp`) — nếu `/tmp` và target ở
khác filesystem (phổ biến trên Linux với tmpfs), `os.replace` sẽ raise `OSError` hoặc
silently fall back to a non-atomic copy+delete. Luôn dùng `mkstemp(dir=target.parent)`.
Pattern chuẩn: xem `state/json_store.py:save` — reuse, không reinvent.
## 2026-06-29 — delivery-6: checkpoint tasks (HUMAN REVIEW GATE) phải được mark [x] trước khi openspec archive

`openspec archive` đếm TẤT CẢ tasks kể cả checkpoint lines. Nếu checkpoint `- [ ]` chưa
được đánh `[x]`, archive hỏi "Warning: N incomplete task(s) found" và default No → bị cancel.
Mark checkpoint tasks `[x]` ngay sau khi human review xong, trước khi chạy archive.
## 2026-06-29 — delivery-6: BrokenPipeError handler phải ở CLI top-level, không phải trong adapter

Catch `BrokenPipeError` bên trong adapter (`StdoutDelivery`) không đủ — interpreter còn có
một final flush của `sys.stdout` khi process exit, xảy ra SAU khi `deliver()` đã return.
Chỉ top-level handler + `os.dup2(devnull, sys.stdout.fileno())` mới suppress được cả hai
điểm. Pattern: `except BrokenPipeError → os.dup2 → Exit(0)` trong `cli.py:run`.
## 2026-06-29 — delivery-6: subagent spawn (kiro_default) bị invalid_redirect_uri — chạy trực tiếp

Trong session này `InvokeSubagents` với `kiro_default`/`developer`/`qa` đều fail ngay lập tức
với `invalid_redirect_uri` (0 tool uses, 0.00s). Khi subagent spawn fail, không retry — chạy
thẳng S4/S5/S6 trong cùng agent context. Không block pipeline vì lý do infra.
