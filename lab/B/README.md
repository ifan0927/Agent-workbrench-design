# B 組實驗：配置實際生效

契約：[B1–B4](../../docs/experiments/b-configuration.md)。結論集中在 [RESULTS.md](RESULTS.md)。這是專案內的 Python 標準函式庫實驗，不是完整工作台配置服務。

## 重跑

在專案根目錄執行；需要 Python 3.11 以上、Codex 0.153.4，以及 A 組已建立的 `agent-workbench-lab-a:0.153.4` Docker image（建置方式見 [A 組](../A/README.md)）。

```sh
# 無模型：快照隔離、選用、同名／缺依賴與模型／工具檢查。
python3 lab/B/test_lab.py

# 由本機固定版本 binary 產生九個介面摘要。
python3 lab/B/contract.py

# 離線核對已保存的真實證據與快照內容。
python3 lab/B/verify.py

# 真實 app-server，容器斷網；不讀認證、不進行模型工作。
python3 lab/B/runner.py --report probe-next.json

# 真實模型，預設只讀 ~/.codex/auth.json；也可指定 --auth-file。
python3 lab/B/runner.py --live --report live-next.json
```

真實模式預設 `gpt-6-astra`／`low`，使用既有 ChatGPT 訂閱；`--model` 可指定模型，但必須通過該次 `model/list` 的模型與推理支援檢查。最多四個模型 turn：A v1、B v2、同一 A thread 再讀 v1，以及不存在模型的負向案例。一般 turn 預設 120 秒（`--seconds 1..180`）；不存在模型最多 45 秒。此為 turn 數與時間上限，不是 token／金額硬上限；報告保存實際 token 用量，不估算未知訂閱成本。逾時會 interrupt，無自動重試或 API fallback。

結果檔名必須尚未存在，避免覆蓋已執行證據。`results/<name>-inputs/` 保存該次合成輸入與組裝 manifest；沒有日常 repo 或使用者指引副本。`.runtime/` 是臨時材料，正常結束會刪除。主機強制中斷後可用 Docker label `agent-workbench.lab=B` 查找遺留容器，核對後逐一清理。

## 實作

| 檔案 | 責任 |
| --- | --- |
| [fixtures.py](fixtures.py) | 產生共用來源與 repo，實體複製選用 skills、固定 v1／v2 快照與內容 hash；檢查缺少／同名能力及模型／工具設定。 |
| [runner.py](runner.py) | 容器生命週期、`config/read`／`skills/list`／`model/list`／MCP 狀態、thread／turn、checkpoint、檔案產物與執行事件比對。 |
| [contract.py](contract.py) | 固定版本 schema 的介面摘要與 hash。 |
| [verify.py](verify.py) | 離線核對實際內容、來源、執行時序、工具事件與錯誤原因；不只讀報告內的 passed 欄位。 |
| [test_lab.py](test_lab.py) | 快照不受來源更新影響、拒絕 symlink 與覆寫、缺失及歧義處理。 |

認證讀取與 stdio RPC 沿用 [A 組 live.py](../A/live.py) 的 `load_auth` 和 [rpc.py](../A/rpc.py)，沒有修改 A 組。只把短效 access token 與帳號欄位經 stdin 注入，認證檔不掛載、不複製、不修改；refresh token 不交給 worker。真實 OAuth 登入／刷新不在本組實作範圍，刷新要求回覆需 host 接手。

容器使用 A 組非 root image、唯讀根目錄、唯讀 repo／配置／skills 掛載；只有 `/out` 成果及暫存路徑可寫。真實 turn 使用 `externalSandbox`，隔離由 Docker 提供。來源更新由 host 寫入獨立合成來源，執行中的 worker 看不到它；checkpoint 在 A 的模型 turn 內觸發更新並產生 B 快照。之後強制重新掃描 A skills、同 thread 再執行，檢查仍讀到 v1 reference。

## 證據界線

- `selected_skills` 是 host 選用清單；原生發現集合另由 `skills/list` 保存。同名必須指出路徑，缺依賴不能從 `enabled: true` 推定可用。
- `instructionSources` 證明原生載入路徑；模式透過 `developerInstructions`，任務透過 `turn.input`，原生 base instructions 保留。產物檢查各來源欄位與刻意衝突，另有唯讀寫入失敗證據。
- 原始 RPC、模型文字、任意命令與 stderr 不寫報告。只留命令 hash、指定 fixture 路徑命中、結束碼、用量、通過比對的合成產物與 hash。
- 缺模型／推理／必要動態工具由 host 預檢明確回報；不存在 permission profile 與模型另探測原生錯誤。任意推理字串會被此版本接受，不能當作有效支援。
- 沒有驗證大型 skills 清單截斷、插件／admin 來源組合、所有模型設定或任意 MCP 功能。這些不由本組的小型案例推廣。

本次介面依據：[官方 app-server](https://learn.chatgpt.com/docs/app-server)、[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[skills](https://learn.chatgpt.com/docs/build-skills)，與實際 0.153.4 schema。官方文件與固定版本可能有欄位差異，以保存的本機介面及實測結果區分。
