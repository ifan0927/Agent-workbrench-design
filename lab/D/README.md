# D 組實驗：外層流程與環境

契約：[D1–D4](../../docs/experiments/d-runtime.md)。結論與限制只維護在 [RESULTS.md](RESULTS.md)。本次已獲授權實作及執行；D4 依使用者指定採 `lab/D` 合成 repo。

這是單主機最小實驗：真正的 LangGraph、SQLite checkpoint、跨程序重啟與 Docker，搭配固定輸出的 worker。人工回答及中斷點由測試注入；不呼叫模型，不讀認證，無訂閱／API 使用量。後續若接入 Codex，可沿用 [A 組](../A/README.md)的本機登入來源與記憶體 token 注入方式，本組不重做認證實驗。

## 重跑

需要 Python 3.11 以上、uv、Git 與可用的本機 Docker Engine。從專案根目錄執行：

```sh
# 所有 Python 依賴限於 lab/D/.venv；uv.lock 固定完整依賴。
uv sync --locked --project lab/D --cache-dir /private/tmp/agent-workbench-d-uv-cache

# 替身 Docker 回應：6 個負向測試，無容器、模型或網路。
lab/D/.venv/bin/python lab/D/test_lab.py

# 真實 Docker + LangGraph；結果路徑必須尚未存在。
lab/D/.venv/bin/python lab/D/validate.py --report lab/D/results/next

# 離線重新核對原始成果、checkpoint、來源雜湊與 Git bundle。
lab/D/.venv/bin/python lab/D/verify.py lab/D/results/next
```

本機須先有 `node:22.22.0-bookworm` image；本次沿用 A 組已有的映像，不拉新版。D4 從固定 Git fixture 建立本次專用 image，無 npm 外部依賴。每個 host 命令最多 45 秒、Docker 操作通常 30 秒、image build 90 秒；這些是觀測界限，不代表觀測逾時就自動重開 worker。失敗後保存已取得的證據並停止本次實驗資源，程式不重送整個工作。

## 實作與控制權

| 檔案 | 責任 |
| --- | --- |
| [flow.py](flow.py) | 唯一流程決策：prepare → dispatch → 等 worker → 收結果 → 等回答／完成；取消先保存，再 stop。 |
| [host.py](host.py) | 單次操作入口：start、status、resume、recover；指定 thread ID，使用 SQLite checkpointer；不決定下一步或自動重試。 |
| [runner.py](runner.py) | 保存 attempt、以固定容器名與 labels 核對身分、啟動、觀測、停止及收集。 |
| [worker.cjs](worker.cjs) | 固定輸出替身；另有忽略 TERM 的父子程序，持續寫 heartbeat 供取消實驗觀測。 |
| [environment.py](environment.py)、[fixture/](fixture/) | 固定本地 Git repo／bundle、image build、兩個獨立測試服務及建置／測試 worker。 |
| [validate.py](validate.py)、[test_lab.py](test_lab.py)、[verify.py](verify.py) | 實際執行、負向模擬與離線證據稽核；不是另一套工作 controller。 |

流程 checkpoint 只保存合成的工作輸入、attempt、回答、狀態與成果索引。執行紀錄保存在另一份 SQLite，只包含身分、啟動階段、容器 ID 與停止要求；不維護下一步或重試規則。每個工作／attempt 的檔案鎖限於一次操作，不鎖 worker 的整段執行；不同工作可並行。

### 中斷與副作用

[LangGraph 官方文件](https://docs.langchain.com/oss/python/langgraph/interrupts)說明 `interrupt()` 恢復會重跑節點開頭；本組讓 prepare 的 checkpoint 先同步落盤，再進 dispatch，等待節點內不啟動容器。流程的持久化使用 [SQLite checkpointer](https://docs.langchain.com/oss/python/langgraph/persistence)，不把它當成容器快照。

每個 attempt 先保存輸入與固定容器名；重進 dispatch 先 inspect，核對 owner、attempt 與已知容器 ID。只啟動 `created` 容器，絕不 start 已退出的容器。啟動意圖已保存但容器不存在時，無法證明工作沒發生，流程結束於 `interrupted` 等待接手。這是避免重複執行的取捨，不宣稱跨主機 exactly-once。

worker 的 `launches.jsonl` 獨立記錄每次進入工作入口；測試對照容器 ID、checkpoint、結果中的 attempt 與此檔案。事件只是通知，不能直接提供被採信的成果；runner 必須讀取綁定該 attempt 的落盤結果與成功退出狀態。舊 attempt 通知、普通留言與錯誤回答不推進新工作。

取消會先將 `cancelling` 存進 checkpoint，再保存停止要求、以指定容器 ID 執行有限等待的 Docker stop，最後 inspect。已確認停止為 `cancelled`；容器消失或觀測失敗為 `cancel_unknown`。停止要求本身不等於已停止。取消不回滾已保存成果。

### D4 環境範圍

fixture 是無外部套件的 Node CommonJS repo，包含 build、兩項 Node tests 與 HTTP 磁碟測試服務。每次固定 commit 並保存可重建 bundle；兩個工作從同一 bundle 取出獨立 checkout，分配專屬 bridge network、資料目錄、barrier 目錄與隨機 localhost port。兩者在 barrier 同時存活，對同一 `/value` 分別寫入不同資料，再同時放行讀回。

Docker 使用非 root、唯讀根目錄、移除 capabilities、限制 PID／記憶體／CPU，不掛 Docker socket 或使用者登入目錄。D1–D3 worker 斷網；D4 採一般 bridge 以支援此主機的 host port mapping，可出網但測試只呼叫內部 HTTP 服務及 localhost，未實作出口白名單或多租戶安全隔離。

## 成果與清理

`results/` 保留精簡報告、來源 hash、合成 checkpoint、啟動／部分成果／結果，以及 D4 build/test 輸出與 Git bundle。`results/validation` 為首輪 D4 失敗證據，`results/validated` 為修正後完整驗證。以 RESULTS.md 指定的結果為準；不要把舊來源 manifest 當成目前程式。

正常與可處理的失敗路徑會清理本次容器、網路、D4 image 與 `.runtime/<run>`，先保留成果。整個驗證主程序遭強制殺死時，可先唯讀檢查：

```sh
docker ps -a --filter label=agent-workbench.lab=D
docker network ls --filter label=agent-workbench.lab=D
```

核對 `lab.d.owner`、實際容器身分與保存成果後，逐一清理本次資源；不使用全機 prune。程序 `os._exit(86)` 只注入到 host 子程序，不中止 Docker daemon 或其他專案。
