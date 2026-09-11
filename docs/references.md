# 來源與證據索引

本頁記錄支持目前候選設計的來源及查核邊界，不保存來源全文。查核日期：2026-09-10；後續實驗前仍需核對固定版本與現行文件。

## 證據身分

| 身分 | 如何使用 |
| --- | --- |
| 使用者基準 | 本次交接與後續明確指示；產品範圍集中在 [product.md](product.md)。 |
| 技術建議 | `design/` 的候選組合與責任分配，不自行成為已接受決策。 |
| 來源事實 | 官方文件或本輪實際讀到的程式；只支持相應機制存在。 |
| 待驗證假設 | 本機行為、並行刷新可靠性、配置生效與成果交接；以 [experiments/](experiments/README.md)追蹤問題，不補寫成功。 |

最初文件整理階段僅有只讀查核；後續已另獲授權進行本專案實驗，實測結果以 [lab 索引](../lab/README.md) 為準，其中配置實測見 [B 組結果](../lab/B/RESULTS.md)。下列原始來源查核紀錄保留其當時範圍；歷史專案的測試紀錄不等於本專案驗收。

## 官方接口與機制

| 來源 | 支持的內容／限制 |
| --- | --- |
| [Codex AGENTS.md](https://developers.openai.com/codex/guides/agents-md/) | 分層、override、啟動發現與大小限制；本專案注入案例的驗收另見 [B 組](../lab/B/RESULTS.md)。 |
| [Codex Skills](https://developers.openai.com/codex/skills/) | 漸進載入、發現來源、同名與初始清單預算；不等於全部技能會被使用。 |
| [Codex Authentication](https://developers.openai.com/codex/auth/) | 訂閱／API 登入、headless 與憑證保存；不把容器範例泛化成所有自動化情境適用。 |
| [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) | Exec、JSONL、結構化輸出、resume 與自動化認證。 |
| [App-server](https://developers.openai.com/codex/app-server/) | Thread／turn、配置／skills 查詢、外部 token 注入與刷新；外部 token 模式仍為 experimental。 |
| [SDK](https://developers.openai.com/codex/sdk/) | 官方 TypeScript 與 Python 接入；不能直接推定安裝版本包含所有最新能力。 |
| [CI/CD 認證](https://learn.chatgpt.com/docs/auth/ci-cd-auth) | 特定 managed auth 流程的序列共用、回存與使用限制；不把它當成所有訂閱使用方式的共同上限。 |
| [API Rate limits](https://platform.openai.com/docs/guides/rate-limits) | API 仍受組織／專案等速率限制；不宣稱 API 無限平行。 |
| [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | Checkpointer／store 分工、等待與節點重新執行；不保存任意程序或保證外部副作用恰好一次。本次 D 組再查核官方文件，固定版本的實測見 [D 組結果](../lab/D/RESULTS.md)。 |
| [Docker Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/) | 持久檔案、唯讀掛載與 daemon 主機路徑語意；不是專案建置可用性的證據。 |
| [FastAPI](https://fastapi.tiangolo.com/)、[Vite](https://vite.dev/guide/) | 後端／前端工具候選入口，不提供工作產品語意。 |

## 認證整合先例

| 來源 | 本次實際取得的證據 |
| --- | --- |
| [Hermes Credential Pools](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-pools)、[Providers](https://hermes-agent.nousresearch.com/docs/integrations/providers/) | 已讀官方專案文件：刷新協調、認證來源與不需 Codex CLI 的 provider；本輪未完成其相關原始碼核讀，亦未實測。 |
| [OpenClaw Codex auth](https://docs.openclaw.ai/plugins/codex-harness-reference/auth) | 已讀外部 token 與認證回呼文件；沒有本機驗收，不將其他 OAuth 路徑的歷史文件混作此接口保證。 |
| [Multica codex_home.go](https://github.com/multica-ai/multica/blob/0c886a1c9e021ba652460de1c8213c8c3027ff2a/server/internal/daemon/execenv/codex_home.go#L194) | 已讀固定上游版本的配置隔離／auth symlink 程式；不能證明並行刷新完全可靠。 |
| [Codex 認證管理程式](https://github.com/openai/codex/blob/b348fc26674189f758d5941cdab3f78f258b2aa7/codex-rs/login/src/auth/manager.rs#L2799) | 已讀固定上游版本的重載認證與程序內刷新鎖；不是本機安裝版本的並行驗收。 |

## 本機背景與查核範圍

以下是本機來源，其他環境不保證存在；按問題選讀，不要求掃描完整歷史或程式。

- 既有研究入口（本機背景資料，未公開）、交接研究（本機背景資料，未公開）、方案選擇（本機背景資料，未公開）、LangGraph 評估（本機背景資料，未公開）：本輪已讀。舊範圍與最新交接衝突時，依本專案產品基準。
- ALC 封存說明（本機背景資料，未公開）：本輪只讀封存說明，未重新稽核程式或驗證歷史里程碑。CodeRail 僅為背景名稱，本輪未直接核讀其程式。
- Multica-local 架構說明（本機背景資料，未公開）、本機 runtime（本機背景資料，未公開）：已讀相關文件與認證掛載程式。Vendor 固定版本為 `4aca890a29576f075dfc5584a1d41dbc507cdb41`，讀到 app-server 啟動與 task home 準備；不把自訂 broker 視為原生 Multica 行為。

最初只讀環境快照：主機回報 macOS ARM64，Codex 安裝套件為 `0.153.4`，Docker client／server 回報 `28.5.2`、server 為 Linux ARM64。這只證明當時套件資訊及 Docker 端點可連線，不代表專案容器、模型或認證已通過驗收。
