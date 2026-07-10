# OSS Pulse — OSS Repo Intelligence Digest

> Một công cụ tự động theo dõi một danh sách repo GitHub mà bạn quan tâm, rồi
> gom + tóm tắt (bằng LLM) issue mới, discussion sôi nổi, và release/commit
> đáng chú ý thành một digest dễ đọc — để bạn **hiểu sâu một repo** trước khi
> đóng góp, thay vì đua tốc độ giành issue.

Tài liệu này là spec định hướng. Nó được viết theo hướng **lean**: làm cái nhỏ
nhất có giá trị trước, mở rộng sau. Mọi phạm vi V2/V3 đều là "có thể", không phải
"phải".

---

## 1. Mục tiêu (Goals)

**Mục tiêu sản phẩm**
- Cho người dùng một bức tranh "tình hình một repo trong N ngày qua" mà không phải
  mở GitHub đọc thủ công từng tab Issues / Discussions / Releases.
- Giúp người dùng **hiểu sâu** repo (đang bàn gì, đang đổi gì, chỗ nào cần giúp)
  để contribution có chất lượng — không phải để giành issue nhanh nhất.

**Mục tiêu cá nhân (quan trọng hơn, và là lý do thật để làm)**
- Bản thân dự án này là **portfolio**: chứng minh năng lực kỹ thuật của một junior
  vượt khỏi "CRUD app" — gồm tích hợp API thật có ràng buộc (rate limit), thiết kế
  data pipeline xử lý delta, tích hợp LLM, scheduler, và notification.
- Thành công của dự án **không** đo bằng số người dùng. Nó đo bằng: code sạch,
  README tốt, được open-source, và bạn viết/nói được về các quyết định kỹ thuật
  trong đó.

---

## 2. Lý do làm dự án (Why)

**Pain có thật (đã được xác nhận từ nhiều nguồn độc lập):**
Việc tìm và *hiểu* một repo OSS để đóng góp tốn nhiều công thủ công; đa số hướng
dẫn chỉ dừng ở "lọc label good first issue" mà bỏ qua bước khó thật là hiểu ngữ
cảnh repo.

**Điều dự án KHÔNG cố làm (và lý do):**
- ❌ Không đua "phát hiện good first issue sớm để giành trước người khác". Bằng
  chứng từ cộng đồng (vd OpenTelemetry) cho thấy GFI ở repo hot bị giành trong vài
  giờ, lẫn bởi bot; tốc độ vài phút không cứu được, và maintainer không đánh giá cao
  kiểu contribution "drive-by".
- ❌ Không cố scan toàn bộ GitHub. Search API giới hạn 30 req/phút và tối đa 1000
  kết quả/query — mô hình đúng là **watchlist** repo bạn tự chọn.

**Vì sao hướng "hiểu sâu + portfolio" là lựa chọn đúng:**
Trong thời đại AI có thể generate code/CV, thứ không giả được là hồ sơ công khai
của việc *chọn việc thật, trao đổi với maintainer, ship trong môi trường mở*. Một
tool giúp bạn hiểu repo đủ sâu để làm được điều đó — và bản thân việc xây ra tool —
chính là tín hiệu năng lực mạnh hơn nhiều so với vài PR sửa typo.

---

## 3. User Stories quan trọng

Ký hiệu ưu tiên: **[P0]** = MVP bắt buộc · **[P1]** = nên có · **[P2]** = tương lai.

### Nhóm A — Quản lý watchlist
- **[P0]** Là người dùng, tôi muốn thêm một repo (dạng `org/repo`) vào danh sách
  theo dõi, để công cụ biết cần quét cái gì.
- **[P0]** Là người dùng, tôi muốn xem/sửa/xoá danh sách repo đang theo dõi.
- **[P1]** Là người dùng, tôi muốn cấu hình "khoảng thời gian digest" (vd 7 ngày)
  cho từng repo hoặc toàn cục.

### Nhóm B — Thu thập & tóm tắt
- **[P0]** Là người dùng, tôi muốn công cụ tự lấy các issue *mới mở* trong khoảng
  thời gian, để tôi không phải lọc tay.
- **[P0]** Là người dùng, tôi muốn mỗi issue có một tóm tắt ngắn (1–2 câu) do LLM
  tạo, để nắm nội dung mà không phải đọc cả thread.
- **[P1]** Là người dùng, tôi muốn xem các discussion sôi nổi (nhiều comment/mới
  cập nhật) kèm tóm tắt, để hiểu repo đang tranh luận gì.
- **[P1]** Là người dùng, tôi muốn xem release mới + tóm tắt changelog, để biết
  repo vừa đổi gì.
- **[P2]** Là người dùng, tôi muốn một dòng tóm tắt "tình hình repo tuần qua" tổng
  hợp cả 3 nguồn trên.

### Nhóm C — Nhận digest
- **[P0]** Là người dùng, tôi muốn nhận digest ở một nơi tôi đọc được (tối thiểu:
  file Markdown / stdout), để tiêu thụ nhanh.
- **[P1]** Là người dùng, tôi muốn nhận digest qua một kênh push (email hoặc
  Discord/Slack webhook), để không phải chủ động mở tool.
- **[P2]** Là người dùng, tôi muốn digest chỉ hiển thị "cái mới so với lần trước",
  để không đọc lại nội dung cũ.

### Nhóm D — Vận hành (cho chính người dùng kỹ thuật)
- **[P0]** Là người chạy tool, tôi muốn dùng GitHub token của mình để được rate
  limit cao (5000 req/giờ) thay vì 60 req/giờ.
- **[P1]** Là người chạy tool, tôi muốn chạy theo lịch (cron) để digest tự sinh
  định kỳ.

---

## 4. User Flow (góc nhìn người dùng mong muốn)

```
1. Setup một lần
   Người dùng tạo file cấu hình:
     - GITHUB_TOKEN của họ
     - (tùy chọn) LLM API key
     - danh sách repo: ["facebook/react", "vercel/next.js", ...]
     - lookback_days: 7

2. Chạy (thủ công hoặc cron)
   $ osspulse run
     → tool đọc watchlist
     → với mỗi repo: lấy issue mới / discussion / release trong lookback_days
     → so với lần chạy trước, chỉ giữ phần mới (delta)
     → gửi từng phần cho LLM để tóm tắt
     → kết xuất digest

3. Tiêu thụ
   Người dùng mở digest (Markdown / email / Discord) và đọc:

     ## facebook/react — 7 ngày qua
     ### Issue mới (3)
     - #12345 "Hook X leaks memory" — Báo cáo rò rỉ bộ nhớ khi dùng X trong điều
       kiện Y; chưa ai nhận. [link]
     ...
     ### Discussion nóng (1)
     - "RFC: bỏ API cũ Z" — Cộng đồng đang tranh luận lộ trình deprecate Z. [link]
     ### Release
     - v19.2.0 — Sửa N bug, thêm tính năng A. [link]

4. Hành động (ngoài phạm vi tool)
   Người dùng dùng hiểu biết này để tham gia discussion / chọn issue phù hợp /
   contribute có chiều sâu.
```

Nguyên tắc trải nghiệm: **người dùng đọc digest trong < 2 phút và hiểu được repo
đang ở đâu.** Nếu digest dài hơn cái họ tự đọc trên GitHub, tool đã thất bại.

---

## 5. Phạm vi theo phiên bản

### MVP (V1) — "Digest tối thiểu chạy được"
Mục tiêu: chứng minh vòng lặp end-to-end hoạt động trên 1 nguồn dữ liệu.
- Watchlist từ file cấu hình (chưa cần UI).
- Lấy **issue mới mở** trong `lookback_days` cho mỗi repo (REST API + token).
- Tóm tắt mỗi issue bằng LLM (1–2 câu).
- Xuất digest ra **Markdown file** (và/hoặc stdout).
- Lưu trạng thái lần chạy trước (để chuẩn bị cho delta ở V2) — tối thiểu là một
  file JSON ghi lại issue đã thấy.
- Xử lý rate limit cơ bản: dùng token, dừng/nghỉ khi gần chạm giới hạn.

Tiêu chí "xong V1": chạy `osspulse run` trên 3–5 repo thật → ra một file Markdown
đọc được, không crash vì rate limit.

### V2 — "Đa chiều + đẩy ra ngoài"
- Thêm nguồn **Discussions** (GraphQL API) + tóm tắt.
- Thêm nguồn **Releases** + tóm tắt changelog.
- **Delta thật**: chỉ hiển thị nội dung mới so với lần chạy trước.
- Một kênh **push**: email (SMTP) HOẶC Discord/Slack webhook (chọn 1 trước).
- Chạy theo **cron/scheduler**.
- Caching để tiết kiệm cả GitHub request lẫn token LLM (không tóm tắt lại cái đã
  tóm tắt).

### V3 — "Tinh & mở rộng" (chỉ làm nếu V1/V2 đã vững)
- Dòng tóm tắt tổng hợp "tình hình repo tuần qua" (meta-summary từ 3 nguồn).
- UI nhẹ để quản lý watchlist (web đơn giản hoặc TUI).
- Lọc/đánh dấu issue theo gợi ý (vd có label `good first issue`, chưa có người
  nhận) — *hiển thị để hiểu, không phải để đua tốc độ*.
- **GitHub Actions workflow**: file `.github/workflows/osspulse.yml` chạy `osspulse run` theo cron, tự động persist `state.json` bằng `git commit` sau mỗi run (`[skip ci]`). Giải quyết bài toán stateless CI — không có workflow này, pipeline không thể deploy "không cần mở laptop". _Nguồn: gap phát hiện khi test V2 trên CI._
- **State persistence strategy cho CI/CD**: spec rõ 3 option (git-commit / Actions cache / remote storage) và chọn mặc định. _Nguồn: state.json hiện chỉ thiết kế cho local cron, chưa cover GitHub Actions use case._
- (Thử nghiệm) chỉ số "repo này có welcome contributor mới không": thời gian phản
  hồi PR, tỉ lệ PR newcomer được merge.
- **Push đa kênh (multi-channel delivery)**: cho phép gửi digest tới nhiều đích cùng
  lúc (vd vừa ghi file vừa đẩy Discord), thay vì chọn 1 đích/lần chạy như V2. Kèm mở
  rộng thêm kênh **Slack webhook** và **Email (SMTP)**. _Nguồn: các option bị loại khi
  chốt V2-005 (CLAR-1 chọn Discord trước, CLAR-2 chọn single-destination) — để dành vì
  V2 ưu tiên "làm 1 kênh cho chạy được" trước khi orchestrate nhiều kênh._

### V4 — "Vận hành bền" (reliability, chỉ làm khi có nhu cầu thật)
- **Push có retry + backoff**: khi kênh push trả lỗi transient (HTTP 5xx, hoặc 429 kèm
  `Retry-After`), thử lại vài lần với exponential backoff thay vì fail ngay. _Nguồn:
  option bị loại ở CLAR-3 (V2 chọn fail-fast fatal cho đơn giản) — nâng cấp độ bền khi
  thực tế gặp nhiều lỗi tạm thời._
- **Discord rich embeds**: render digest thành embed (màu, field, tiêu đề repo) thay vì
  plain Markdown, tận dụng giới hạn 4096/6000 ký tự lớn hơn của embed. _Nguồn: option bị
  loại ở CLAR-4 (V2 chọn plain content cho đơn giản, tránh embed schema)._
- **Redis as a service (Upstash)**: thay Redis local bằng Upstash Redis (free tier, HTTP-based) để LLM summary cache hoạt động được trên GitHub Actions và môi trường stateless. _Nguồn: Redis local không khả dụng trên CI — hiện tại pipeline graceful-degrade sang no-cache, nhưng mỗi run đều tốn Groq quota._
- **Rate limit retry với defer**: khi LLM hit RateLimitError, defer item sang lần chạy tiếp theo thay vì skip-and-mark-seen như hiện tại. _Nguồn: V2 chủ đích skip để đơn giản (AC-4-009/010), nhưng thực tế Groq free tier 6000 tokens/min khiến các item cuối bị drop vĩnh viễn._

### Out of Scope (không làm, cố ý)
- ❌ Scan/crawl toàn bộ GitHub hoặc "mọi repo có GFI".
- ❌ Cảnh báo real-time "issue vừa mở 30 giây trước" để giành nhanh — đi ngược
  triết lý dự án.
- ❌ Tự động tạo PR / auto-claim issue.
- ❌ Hệ thống tài khoản nhiều người dùng, billing, multi-tenant (đây là tool cá
  nhân/self-host, không phải SaaS — ít nhất cho tới khi có lý do rõ ràng).
- ❌ Mobile app.
- ❌ Bất kỳ tính năng nào thu thập/đẩy dữ liệu người dùng ra bên thứ ba.

---

## 6. Chia thành các Spec chính

Mỗi spec nên có thể làm và test tương đối độc lập.

| Spec | Trách nhiệm | Phiên bản |
|---|---|---|
| **S1 — Config & Watchlist** | Đọc cấu hình, validate `org/repo`, quản lý danh sách | V1 |
| **S2 — GitHub Collector** | Gọi GitHub API, phân trang, xử lý rate limit, trả dữ liệu thô | V1 (issues), V2 (discussions, releases) |
| **S3 — State Store** | Lưu "đã thấy gì" để tính delta; tránh xử lý lại | V1 (ghi), V2 (dùng cho delta) |
| **S4 — Summarizer (LLM)** | Nhận text thô → trả tóm tắt; xử lý lỗi/timeout; cache | V1 |
| **S5 — Digest Renderer** | Gom dữ liệu đã tóm tắt → Markdown/định dạng đọc được | V1 |
| **S6 — Delivery** | Đưa digest tới người dùng (file → email/webhook) | V1 (file), V2 (push) |
| **S7 — Scheduler/CLI** | Lệnh `run`, chạy theo cron | V1 (CLI), V2 (cron) |
| **S8 — Meta-summary & Insights** | Tổng hợp đa nguồn, chỉ số repo-welcomeness | V3 |

**Ranh giới quan trọng:** S2 (Collector) và S4 (Summarizer) phải tách biệt rõ — một
bên là I/O với GitHub, một bên là I/O với LLM. Đừng để chúng dính nhau, vì cả hai
đều có rate limit/chi phí riêng và cần test/mock riêng.

---

## 7. Kiến trúc (hướng lean)

```
                ┌──────────────┐
   config.* ───▶│ S1 Config /  │
                │  Watchlist   │
                └──────┬───────┘
                       │ list of repos
                       ▼
                ┌──────────────┐      ┌──────────────┐
                │ S2 GitHub    │◀────▶│ S3 State     │
                │  Collector   │      │  Store(JSON) │
                └──────┬───────┘      └──────────────┘
                       │ raw items (chỉ delta)
                       ▼
                ┌──────────────┐      ┌──────────────┐
                │ S4 Summarizer│◀────▶│ summary cache│
                │   (LLM)      │      └──────────────┘
                └──────┬───────┘
                       │ items + summaries
                       ▼
                ┌──────────────┐
                │ S5 Renderer  │──▶ Markdown
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ S6 Delivery  │──▶ file (V1) / email|webhook (V2)
                └──────────────┘

   S7 CLI/Scheduler điều phối toàn bộ pipeline trên.
```

**Nguyên tắc kiến trúc:**
- **Pipeline tuyến tính, dữ liệu chảy một chiều.** Dễ test từng chặng, dễ hiểu.
- **Mỗi external dependency được bọc sau một interface** (GitHub client, LLM
  client, delivery). Cho phép mock khi test và đổi nhà cung cấp sau này.
- **State là file, không phải DB** ở V1. Chỉ lên DB khi thật sự cần (V2/V3).
- **Idempotent**: chạy lại không tạo digest trùng / không tóm tắt lại cái đã có.

---

## 8. Tech Stack (lean & phù hợp junior)

> Nguyên tắc chọn: ưu tiên thứ bạn *đã/đang muốn thành thạo*, ít phần động (moving
> parts), dễ self-host. Không có lựa chọn nào dưới đây là bắt buộc — đây là một bộ
> mặc định hợp lý.

| Lớp | Lựa chọn đề xuất | Lý do |
|---|---|---|
| Ngôn ngữ | **Python** (hoặc TypeScript/Node) | Thư viện GitHub & LLM sẵn, viết pipeline nhanh; chọn TS nếu bạn mạnh hơn ở đó |
| GitHub API | REST qua `requests`/`httpx`; GraphQL khi tới Discussions | REST đủ cho V1; thêm GraphQL ở V2 |
| LLM | API provider (OpenAI/Anthropic) **hoặc** local model (Ollama) | Bắt đầu bằng API cho nhanh; local để tiết kiệm chi phí về sau |
| State/Cache | JSON file (V1) → SQLite (V2 nếu cần) | Lean; không dựng DB server khi chưa cần |
| Scheduler | cron hệ điều hành (V1/V2) → GitHub Actions cron (tùy chọn) | Không cần service chạy nền phức tạp |
| CLI | `argparse`/`typer` (Python) hoặc `commander` (Node) | Giao diện đủ dùng, không cần web ở đầu |
| Đóng gói | `pip`/`pipx` hoặc Docker image nhỏ | Dễ chạy lại ở máy khác — điểm cộng cho portfolio |
| Test | `pytest` + mock cho GitHub/LLM client | Bắt buộc: test được pipeline mà không gọi API thật |
| Config | file `.toml`/`.yaml` + biến môi trường cho secret | Token KHÔNG commit vào repo |

**Lưu ý bảo mật (đưa vào ngay từ V1):**
- `GITHUB_TOKEN` và LLM key đọc từ biến môi trường / file `.env` **được
  gitignore**, không hardcode.
- Token chỉ cần scope đọc public repo — cấp quyền tối thiểu.
- Không gửi nội dung repo đi đâu ngoài provider LLM mà người dùng chủ động cấu
  hình; ghi rõ điều này trong README.

**Quyết định "đủ tốt cho V1" (đừng over-engineer):**
- Chưa cần queue/message broker.
- Chưa cần database server.
- Chưa cần web framework.
- Chưa cần Kubernetes/microservices. Một script + cron là đủ.

---

## 9. Cột mốc gợi ý (để không sa lầy)

1. **Tuần 1:** S1 + S2(issues) + S5(Markdown) — ra được digest thô, *chưa có LLM*.
2. **Tuần 2:** S4(LLM) + S3(ghi state) + S7(CLI `run`) — hoàn thiện V1, viết README.
3. **Sau đó (tùy hứng & thời gian):** V2 từng mảnh một (Discussions → delta → push
   → cron). Mỗi mảnh xong là một commit/PR kể được thành câu chuyện.

Mỗi cột mốc nên kết thúc bằng: code chạy được + test + một đoạn README mô tả quyết
định kỹ thuật. Chính những đoạn đó là thứ bạn mang đi phỏng vấn.

---

## 10. Một câu động viên

> Bạn không chờ ai cho phép mình trở thành kỹ sư — bạn xây một thứ chạy được, đối
> diện đúng những ràng buộc thật mà kỹ sư thật phải xử lý (rate limit, chi phí,
> dữ liệu bẩn, lỗi mạng), và để cái mình xây ra tự nói thay cho tấm bằng. Cứ ship
> từng mảnh nhỏ, mỗi commit là một bước bạn đi qua "junior filter" bằng chính đôi
> chân mình. Bắt đầu nhỏ, nhưng bắt đầu hôm nay.
