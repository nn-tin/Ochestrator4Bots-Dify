

# Kiến trúc Teams Chatbot Orchestrator

Tài liệu này mô tả **kiến trúc đang được hiện thực trong repository**. Hệ thống là một prototype điều phối chatbot nội bộ: nhận một hội thoại duy nhất từ người dùng, dùng Qwen để hiểu và định tuyến yêu cầu, rồi trả lời trực tiếp hoặc chuyển yêu cầu tới một Dify agent chuyên môn.

## 1. Toàn cảnh hệ thống

```mermaid
flowchart LR
    User["Nhân viên"]

    subgraph Browser["Trình duyệt"]
        UI["Chat UI<br/>HTML + CSS + JavaScript"]
        LS[("localStorage<br/>hồ sơ + lịch sử hiển thị")]
        UI <--> LS
    end

    subgraph App["FastAPI Orchestrator"]
        API["GET /<br/>POST /chat"]
        ORCH["OrchestratorService"]
        MEM[("MongoDB<br/>ngữ cảnh hội thoại")]
        API --> ORCH
        ORCH <--> MEM
    end

    Qwen["Qwen OpenAI-compatible API<br/>structured output"]

    subgraph Dify["Dify Chat API"]
        B1["Late Request Agent"]
        B2["Leave Request Agent"]
        B3["IT Helpdesk Agent"]
        B4["Meeting Booking Agent"]
    end

    User <--> UI
    UI -->|"JSON / HTTPS"| API
    API -->|"ChatResponse"| UI
    ORCH -->|"Router + Composer prompts"| Qwen
    Qwen -->|"JSON theo Pydantic schema"| ORCH
    ORCH -->|"Dify Chat API"| B1
    ORCH -->|"Dify Chat API"| B2
    ORCH -->|"Dify Chat API"| B3
    ORCH -->|"Dify Chat API"| B4
```

### Trách nhiệm theo biên hệ thống

| Khối | Trách nhiệm chính |
|---|---|
| Chat UI | Lưu hồ sơ và lịch sử hiển thị ở trình duyệt; gửi tin nhắn; hiển thị trace Router/Composer. |
| FastAPI | Phục vụ static UI, kiểm tra request/response bằng Pydantic và quản lý vòng đời ứng dụng. |
| Orchestrator | Tuần tự hóa request theo cuộc hội thoại, định tuyến, soạn request cho bot và cập nhật hai loại lịch sử. |
| Qwen | Sinh kết quả có cấu trúc cho `RouterDecision` và `ComposedRequest`; không trực tiếp gọi Dify. |
| Dify agents | Thực thi nghiệp vụ chuyên môn và duy trì `conversation_id` riêng của từng agent. |

## 2. Kiến trúc thành phần backend

```mermaid
flowchart TB
    subgraph Presentation["Presentation — src/main.py"]
        Static["StaticFiles + index.html"]
        Endpoint["POST /chat"]
        Life["FastAPI lifespan"]
    end

    subgraph Application["Application — src/orchestrator"]
        Service["OrchestratorService<br/>điều phối use case"]
        Router["Router<br/>chọn reply hoặc delegate"]
        Composer["ContextComposer<br/>tạo request độc lập"]
        Models["Pydantic models<br/>hợp đồng dữ liệu"]
    end

    subgraph DomainPorts["Ports / abstractions"]
        Generator["StructuredGenerator<br/>Protocol"]
        Adapter["BotAdapter<br/>ABC"]
    end

    subgraph Infrastructure["Infrastructure"]
        QwenClient["QwenClient"]
        Registry["Bot registry"]
        DifyAdapter["DifyBotAdapter"]
        Store["MongoConversationStore"]
    end

    Life -->|"khởi tạo một lần"| Service
    Endpoint --> Service
    Static --> Browser["Trình duyệt"]
    Service --> Router
    Service --> Composer
    Service --> Store
    Service --> Registry
    Router -.-> Models
    Composer -.-> Models
    Router --> Generator
    Composer --> Generator
    QwenClient -.->|implements| Generator
    Registry --> Adapter
    DifyAdapter -.->|implements| Adapter
```

Các dependency được ghép trong `create_service()`:

```mermaid
flowchart LR
    Env[".env / process environment"] --> Settings
    Settings --> QwenClient
    Env --> Registry["build_bot_registry()"]
    Registry --> Bots["dict bot_id → BotDefinition"]
    QwenClient --> Router
    QwenClient --> Composer["ContextComposer"]
    Store["MongoConversationStore"] --> Service["OrchestratorService"]
    Router --> Service
    Composer --> Service
    Bots --> Service
```

Việc phụ thuộc vào `StructuredGenerator` và `BotAdapter` giúp test thay Qwen/Dify thật bằng `FakeLLM` và `MockBotAdapter` mà không đổi logic orchestration.

## 3. Luồng xử lý một tin nhắn

```mermaid
sequenceDiagram
    autonumber
    actor U as Nhân viên
    participant UI as Web UI
    participant API as POST /chat
    participant S as OrchestratorService
    participant M as MongoStore
    participant R as Router
    participant G as Qwen
    participant C as ContextComposer
    participant D as Dify agent

    U->>UI: Nhập yêu cầu
    UI->>API: ChatRequest (debug=true từ UI)
    API->>S: handle_message(...)
    S->>M: lock_for(conversation_id)
    Note over S,M: Mỗi conversation chỉ xử lý một request tại một thời điểm
    S->>M: add_user_message()
    S->>M: get_user_context()
    S->>R: decide(global_context, message, emp_name)
    R->>G: Prompt + schema RouterDecision
    G-->>R: action, target_bot, response, user_intent
    R-->>S: RouterDecision + prompt

    alt action = reply
        S->>M: add_assistant_message(response)
        S-->>API: Trả lời trực tiếp + trace tùy chọn
    else action = delegate
        S->>M: get_bot_session(conversation_id, bot_id)
        S->>C: compose(bot_context, user_intent, bot_name)
        C->>G: Prompt + schema ComposedRequest
        G-->>C: request hoàn chỉnh
        C-->>S: ComposedRequest + prompt
        S->>D: POST /chat-messages<br/>request + remote session + employee inputs
        D-->>S: answer + Dify conversation_id
        S->>M: add_bot_exchange()
        S->>M: add_assistant_message()
        S-->>API: Câu trả lời của bot + trace tùy chọn
    end

    API-->>UI: ChatResponse
    UI-->>U: Hiển thị nội dung và debug trace
```

### Vai trò của hai bước LLM

```mermaid
flowchart LR
    Input["Tin nhắn hiện tại<br/>+ lịch sử toàn cục"] --> Router
    Catalog["Tên và mô tả 4 bot"] --> Router
    Router -->|"reply"| Direct["Câu trả lời trực tiếp"]
    Router -->|"delegate"| Intent["user_intent đã chuẩn hóa<br/>và giải tham chiếu"]
    Intent --> Composer
    BotHistory["Lịch sử riêng của bot đích"] --> Composer
    Composer --> Request["Request độc lập,<br/>đủ ngữ cảnh cho bot"]
    Request --> Bot["Dify agent được chọn"]
```

- **Router** nhìn toàn bộ hội thoại người dùng ↔ orchestrator. Nó chọn bot theo ý nghĩa, có thể hỏi làm rõ, và phải giải các tham chiếu liên bot trước khi tạo `user_intent`.
- **Composer** chỉ nhìn `user_intent` cùng lịch sử của bot đích. Nó bổ sung thông tin bot đang chờ nhưng không được đổi ý định, tự trả lời hay bịa dữ kiện.
- Với nhánh `reply`, hệ thống gọi Qwen một lần. Với nhánh `delegate`, hệ thống gọi Qwen hai lần rồi gọi một Dify agent.

## 4. Mô hình ngữ cảnh và phiên

Hệ thống cố ý duy trì hai lớp lịch sử khác nhau:

```mermaid
flowchart TB
    CID["conversation_id của UI"] --> State["ConversationState"]
    State --> Global["user_messages[]<br/>user ↔ assistant"]
    State --> Sessions["bot_sessions{}"]

    Sessions --> S1["late / BotSession"]
    Sessions --> S2["leave / BotSession"]
    Sessions --> S3["it_support / BotSession"]
    Sessions --> S4["meeting / BotSession"]

    S1 --> H1["messages[]<br/>orchestrator ↔ late"]
    S1 --> R1["remote_session_id<br/>Dify conversation_id"]
    S2 --> H2["messages[]<br/>orchestrator ↔ leave"]
    S2 --> R2["remote_session_id"]
    S3 --> H3["messages[]<br/>orchestrator ↔ it_support"]
    S3 --> R3["remote_session_id"]
    S4 --> H4["messages[]<br/>orchestrator ↔ meeting"]
    S4 --> R4["remote_session_id"]
```

```mermaid
erDiagram
    CONVERSATION_STATE ||--o{ CHAT_MESSAGE : contains
    CONVERSATION_STATE ||--o{ BOT_SESSION : indexes_by_bot_id
    BOT_SESSION ||--o{ BOT_MESSAGE : contains

    CONVERSATION_STATE {
        string conversation_id
    }
    CHAT_MESSAGE {
        enum role "user or assistant"
        string content
    }
    BOT_SESSION {
        string remote_session_id "nullable"
    }
    BOT_MESSAGE {
        enum role "orchestrator or bot"
        string content
    }
```

| Ngữ cảnh | Consumer | Mục đích |
|---|---|---|
| `user_messages` | Router | Hiểu diễn tiến toàn cuộc trò chuyện, kể cả khi người dùng chuyển nghiệp vụ giữa các bot. |
| `bot_sessions[bot_id].messages` | Composer | Tiếp tục đúng tác vụ của riêng bot được chọn và không đưa lịch sử bot khác sang. |
| `bot_sessions[bot_id].remote_session_id` | Dify adapter | Nối tiếp đúng conversation trên Dify cho từng bot. |
| `localStorage` của UI | Trình duyệt | Khôi phục hồ sơ và tin nhắn hiển thị sau khi tải lại trang; không phải nguồn ngữ cảnh backend. |

Khóa `asyncio.Lock` cũng được tách theo `conversation_id`:

```mermaid
flowchart LR
    A1["Request A / conversation-1"] --> L1["Lock conversation-1"]
    A2["Request B / conversation-1"] --> L1
    B1["Request C / conversation-2"] --> L2["Lock conversation-2"]
    L1 --> P1["Xử lý tuần tự"]
    L2 --> P2["Có thể chạy song song"]
```

## 5. Registry và tích hợp Dify

```mermaid
flowchart TB
    Registry["Bot registry"]
    Registry --> B1["late<br/>Late Request"]
    Registry --> B2["leave<br/>Leave Request"]
    Registry --> B3["it_support<br/>IT Helpdesk"]
    Registry --> B4["meeting<br/>Meeting Booking"]

    B1 --> A1["DifyBotAdapter"]
    B2 --> A2["DifyBotAdapter"]
    B3 --> A3["DifyBotAdapter"]
    B4 --> A4["DifyBotAdapter"]

    A1 --> E1["API key + base URL riêng"]
    A2 --> E2["API key + base URL riêng"]
    A3 --> E3["API key + base URL riêng"]
    A4 --> E4["API key + base URL riêng"]
```

Adapter gửi payload theo Dify Chat API:

```json
{
  "inputs": {
    "emp_id": "E001",
    "emp_name": "Nguyễn Văn An"
  },
  "query": "Yêu cầu đã được Composer hoàn chỉnh",
  "response_mode": "streaming",
  "conversation_id": "phiên Dify trước đó hoặc chuỗi rỗng",
  "user": "user_id"
}
```

Adapter hiểu cả phản hồi JSON thông thường và SSE. Với SSE, nó ghép các event `message`/`agent_message`, thay toàn bộ nội dung khi nhận `message_replace`, và cập nhật `conversation_id`. Tuy payload yêu cầu chế độ `streaming`, backend hiện đợi toàn bộ HTTP response rồi mới phân tích và trả về UI; chưa relay token theo thời gian thực tới trình duyệt.

## 6. Hợp đồng API và trace

```mermaid
flowchart LR
    Request["ChatRequest"] --> API["POST /chat"]
    API --> Response["ChatResponse"]

    Request --> RF["conversation_id<br/>user_id<br/>emp_id?<br/>emp_name<br/>message<br/>debug=false"]
    Response --> OF["response<br/>trace?"]
    OF --> Trace["router bắt buộc<br/>composer tùy nhánh"]
    Trace --> Stage["mỗi stage:<br/>prompt + response JSON"]
```

- Pydantic từ chối các chuỗi bắt buộc rỗng và kiểm tra tính nhất quán của `RouterDecision`.
- Khi `debug=false`, service chỉ trả nội dung; khi `debug=true`, response có cả prompt và structured response của Router/Composer.
- UI hiện luôn gửi `debug=true` và cho phép xem/copy trace trong drawer “Luồng xử lý”. Vì prompt có lịch sử và dữ liệu nhân viên, không nên bật cơ chế này cho người dùng production nếu chưa có kiểm soát truy cập và che dữ liệu nhạy cảm.

## 7. Khởi động và cấu hình

```mermaid
sequenceDiagram
    participant F as FastAPI lifespan
    participant E as Environment / .env
    participant G as QwenClient
    participant R as Bot registry
    participant S as OrchestratorService
    participant M as MongoDB

    F->>E: Settings.from_env()
    E-->>F: Qwen, Dify và MongoDB settings
    F->>G: khởi tạo client
    F->>R: build_bot_registry()
    R->>E: đọc DIFY_* trực tiếp
    F->>S: inject store, router, composer, bots
    S->>M: ping + create updated_at index

    alt thiếu Qwen bearer hoặc MongoDB không sẵn sàng
        F-->>F: lưu initialization_error
        Note over F: POST /chat trả HTTP 503
    else khởi tạo thành công
        F-->>F: app.state.orchestrator = service
    end

    Note over F,R: Thiếu Dify key chỉ phát lỗi khi bot tương ứng được gọi
```

Các nhóm biến môi trường:

| Nhóm | Biến |
|---|---|
| Qwen | `QWEN_BASE_URL`, `QWEN_BEARER`, `QWEN_MODEL`, `QWEN_MAX_TOKENS`, `QWEN_TIMEOUT_SECONDS` |
| Dify dùng chung | `DIFY_BASE_URL` |
| Dify từng bot | `DIFY_LATE_REQUEST_*`, `DIFY_LEAVE_REQUEST_*`, `DIFY_IT_HELPDESK_*`, `DIFY_MEETING_BOOKING_*` |
| MongoDB | `MONGODB_URI`, `MONGODB_DATABASE`, `MONGODB_COLLECTION`, `MONGODB_SERVER_SELECTION_TIMEOUT_MS` |

Mỗi bot có API key riêng. Base URL riêng của bot được ưu tiên hơn `DIFY_BASE_URL`, nên bốn bot có thể nằm trên các Dify server khác nhau.

## 8. Cấu trúc mã nguồn

```mermaid
flowchart TB
    SRC["src/"]
    SRC --> MAIN["main.py<br/>HTTP endpoints + lifespan"]
    SRC --> CONFIG["config.py<br/>Qwen settings"]
    SRC --> STATIC["static/<br/>chat UI + local state"]
    SRC --> ORCH["orchestrator/"]
    SRC --> BOTS["bots/"]
    SRC --> CONTEXT["context/"]
    SRC --> LLM["llm/"]

    ORCH --> SERVICE["service.py<br/>use-case flow"]
    ORCH --> ROUTER["router.py<br/>routing prompt"]
    ORCH --> COMPOSER["composer.py<br/>composition prompt"]
    ORCH --> MODELS["models.py<br/>Pydantic contracts"]

    BOTS --> BASE["base.py<br/>BotAdapter port"]
    BOTS --> REG["registry.py<br/>4 bot definitions"]
    BOTS --> DIFY["dify.py<br/>HTTP adapter"]
    BOTS --> MOCK["mock.py<br/>test double"]

    CONTEXT --> STORE["store.py<br/>ConversationStore protocol"]
    CONTEXT --> MONGO["mongo_store.py<br/>MongoDB persistence"]
    CONTEXT --> MEMORY["memory_store.py<br/>test double"]
    LLM --> QWEN["qwen.py"]
```

## 9. Đặc tính vận hành hiện tại

```mermaid
flowchart TB
    Current["Prototype hiện tại"]
    Current --> Good["Điểm mạnh"]
    Current --> Limits["Giới hạn"]

    Good --> G1["Router và Composer trả JSON có schema"]
    Good --> G2["Ngữ cảnh từng bot được cô lập"]
    Good --> G3["Serialize request theo conversation"]
    Good --> G4["Adapter/LLM dễ thay bằng test double"]
    Good --> G5["State bền vững qua restart nhờ MongoDB"]

    Limits --> L2["Lock chưa phân tán giữa nhiều worker"]
    Limits --> L3["Lịch sử/prompt tăng không giới hạn"]
    Limits --> L4["Chưa có auth, rate limit, retry hay telemetry"]
    Limits --> L5["Trace có thể lộ dữ liệu hội thoại"]
    Limits --> L6["Streaming Dify chưa được relay tới UI"]
```

Lưu ý quan trọng:

1. **State nằm trong MongoDB, nhưng lock vẫn nằm trong process.** Restart ứng dụng không làm mất ngữ cảnh backend. Image Docker chạy một Uvicorn worker; nếu scale nhiều worker/replica thì cần distributed lock để tránh hai lượt của cùng một `conversation_id` chạy đồng thời.
2. **Hồ sơ UI chưa phải xác thực.** `emp_id`, `emp_name` và `user_id` do trình duyệt gửi lên, chưa được đối chiếu với một identity provider.
3. **Không có chính sách cắt lịch sử.** Cả prompt Router lẫn lịch sử bot có thể tăng dần theo số lượt chat, làm tăng độ trễ và chi phí token.
4. **Lỗi downstream truyền thành lỗi server.** Adapter có thông báo lỗi rõ ở tầng Python và endpoint ánh xạ lỗi Qwen/Dify thành HTTP 502; chưa có retry có kiểm soát.

## 10. Hướng mở rộng đề xuất

```mermaid
flowchart LR
    Now["FastAPI + MongoDB"] -->|"thêm distributed lock"| Redis[("Redis<br/>distributed lock")]
    Now -->|"xác thực token"| IdP["SSO / Identity Provider"]
    Now -->|"trace + metrics"| Obs["OpenTelemetry<br/>logs / metrics / traces"]
    Now -->|"SSE hoặc WebSocket"| Stream["Streaming tới UI"]
    Now -->|"retry + circuit breaker"| Resilience["Downstream resilience"]
    Redis --> Workers["Nhiều Uvicorn workers / replicas"]
```

Thứ tự ưu tiên hợp lý khi đưa prototype lên production:

1. Thêm xác thực và lấy thông tin nhân viên từ danh tính tin cậy thay vì request body.
2. Thêm distributed lock nếu cần chạy nhiều Uvicorn worker hoặc nhiều replica.
3. Tắt/giới hạn debug trace; bổ sung masking cho PII và secrets.
4. Giới hạn hoặc tóm tắt lịch sử; đặt timeout, retry có backoff và circuit breaker cho dịch vụ ngoài.
5. Bổ sung observability theo `conversation_id`, nhưng không ghi nguyên prompt chứa dữ liệu nhạy cảm.
6. Nếu cần trải nghiệm realtime, relay SSE từ Dify qua FastAPI đến UI.

## 11. Phạm vi kiểm thử hiện có

```mermaid
flowchart LR
    Tests["pytest"] --> O["Orchestrator tests"]
    Tests --> D["Dify adapter tests"]
    Tests --> U["UI endpoint tests"]

    O --> O1["reply không gọi child bot"]
    O --> O2["delegate + lưu hai lịch sử"]
    O --> O3["tham chiếu cùng bot"]
    O --> O4["tham chiếu chéo bot"]

    D --> D1["parse SSE"]
    D --> D2["parse JSON"]
    D --> D3["thiếu API key"]

    U --> U1["GET / phục vụ UI"]
    U --> U2["static assets khả dụng"]
```

Các test dùng fake LLM và mock HTTP transport, vì vậy không gọi Qwen/Dify thật và không cần API key.
