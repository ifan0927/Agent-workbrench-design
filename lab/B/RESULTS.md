# B 組驗證結果

驗證日期：2026-09-10。B1–B4 已完成本組最小實驗；這是有條件的技術結論，不代表完整配置服務已實作。固定 Codex 0.153.4、`gpt-6-astra`／`low`，沿用 A 組 image 與本機 ChatGPT 登入。

主要證據：程式版本指紋（本機證據：`results/source-manifest.json`）、測試摘要（本機證據：`results/tests.json`）、真實執行（本機證據：`results/live.json`）、獨立完成核對（本機證據：`results/audit.json`）、無模型探測（本機證據：`results/probe-validated.json`）、本機介面摘要（本機證據：`results/contract.json`）。重跑見 [README](README.md)。

| 項目 | 結果 | 已驗證內容與界線 |
| --- | --- | --- |
| B1 指引分層與衝突 | 通過本案例 | `instructionSources` 依序列出 `/codex-home/AGENTS.md`、`/work/AGENTS.md`；模式另以 `developerInstructions`，任務以 `turn.input` 傳入。三份檔案產物均保有 common／repo 欄位，任務覆蓋 `layered`；刻意要求 `priority=task` 時，產物仍依模式成為 `priority=mode`。不是只讀 agent 自述。 |
| B2 skills 集合與行為 | 通過，集合確實不同 | host 選用 2 項、原生發現 6 項。repo／使用者 home 各額外帶入能力，同名 `b-twin` 有兩個獨立路徑。缺 MCP 依賴的 skill 仍 enabled，另有 malformed skill 的解析錯誤。真實命令讀取選用 skill、指定 repo twin，並成功執行 proof 腳本；產物為 repo twin 與正確版本 proof。 |
| B3 共用配置更新 | 通過此快照方式 | A turn 開始後 6.54 秒，由模型呼叫 checkpoint，host 將共用來源更新為 v2 並產生 B 快照。A 仍讀 v1；B 啟動後讀 v2。A 原 app-server／thread 保持存活，force reload skills 後再次執行仍讀 v1。檔案 hash 不變，reference／腳本與最終產物互相核對。 |
| B4 模型、推理與工具 | 通過，須 host 檢查 | `config/read`／`thread/start` 回覆有效 `gpt-6-astra`／`low`，三個 turn 完成。兩個 worker 均實際呼叫 host 動態工具。host 用原生模型目錄拒絕不存在模型／不支援推理值，並檢查必要工具。不存在 permission profile 原生回覆 `-32600`；不存在模型的 thread 可建立，但真實 turn 失敗且錯誤包含該模型名稱。 |

保護檔案另有容器內實際 append 嘗試，回覆 `EROFS`；repo／配置／skills 的唯讀掛載與前後 hash 證明必要寫入限制。這個實驗保護是 Docker 執行限制，不能只靠 AGENTS.md 保證。

## B2 的四個集合

| 層次 | 本次觀測 |
| --- | --- |
| host 選用 | `b-selected`、`b-twin`。未選用的 library `b-unselected` 沒有複製、沒有被發現。 |
| 原生可發現 | 選用的兩項，加上 repo twin、repo extra、repo missing、user extra，共 6 項；同名不合併。此 image 未觀察到 system／admin／插件 skill。 |
| 實際使用證據 | A／B 的命令事件含選用 SKILL.md 讀取；三次均有腳本命令、成功結束碼，以及 repo twin 路徑。未觀察到 extra／unselected 路徑命中，這不等於完整檔案存取審計。 |
| 正確遵循 | 三個 `/out/receipt.json` 均通過完整 JSON 比對。報告保留核對後的合成物件與原始檔案 hash，不保存任意模型文字。 |

缺依賴 skill 的 metadata 宣告 `b_absent`，實際 MCP 狀態沒有它，host 預檢回報 `missing_dependency`；不啟動該 skill 的模型工作、不自動安裝依賴。以名稱選取 twin 時回報 `ambiguous`，本次任務明確指定 repo 路徑才執行。

登入後另外觀察到原生 `codex_apps` MCP server。隔離 CODEX_HOME 並不等於工具集合只有 host 宣告的 dynamic tools；本次未測其連線／工具行為，也沒有把它的存在當成工具可用證據。必要 checkpoint 的可用性是由真正回呼證明。

## B3 的快照邊界

每份快照實體複製共用約定、repo、選用 skills 全目錄（含 scripts／references）、使用者測試 skill、模式與任務；manifest 保存來源及快照 hash、組裝順序、要求的模型／工具。組裝拒絕 source symlink，避免 worker 後續讀到可變來源。

A 只掛載自己的快照，不掛共享來源；來源更新不會改變 A 的原生檔案監看輸入。驗證涵蓋更新當下的 turn，以及同 thread 下一個 turn 的強制重新發現。這不證明 Codex 直接掛可變共用目錄時也會自行固定內容；快照邊界由 host 負責。

保存的組裝內容：A v1 manifest（本機證據：`results/live-inputs/snapshot-a/manifest.json`）、B v2 manifest（本機證據：`results/live-inputs/snapshot-b/manifest.json`）。此工作目錄沒有 Git repository metadata，因此本次來源以檔案 hash 識別，沒有虛構 commit。

## B4 的錯誤與有效值

首輪 probe.json（本機證據：`results/probe.json`） 與補充 probe-corrected.json（本機證據：`results/probe-corrected.json`） 均為斷網／無認證探測，保留錯誤假設的證據：原先假設無效推理字串會在 thread 或 turn 入口被拒絕，實際 0.153.4 會接受，thread 甚至回傳相同任意字串。第二次探測的無效 turn 在無網路容器中接受後隨容器清理結束；未進行真實模型驗證。

因此最終 runner 使用 `model/list.supportedReasoningEfforts` 做 host 預檢，而不把「已接受」視為支援。一般 CLI 入口另以 rejected-model.json（本機證據：`results/rejected-model.json`） 證明在模型工作前拒絕不存在模型並保存清楚診斷。最終無模型／真實報告都保存 `reasoning_effort_unavailable`、`model_unavailable`、`required_tool_missing`。這是 host 明確拒絕的證據，與原生錯誤分開標示。

`thread/start` 有效回覆、完成事件與工具行為是本次 runtime 層證據；沒有直接檢查供應商內部推理執行。`web_search=disabled` 經 config 查詢確認，但未做所有工具的排除測試，也不是網路目的地白名單。

## 驗證與用量

- 5 個無模型測試通過：更新隔離／未選用排除／拒絕覆寫、symlink 拒絕、能力缺失與歧義、模型／工具 gate，以及完成核對對錯誤模型原因和篡改快照的拒絕。
- 9 個固定版本 schema 介面已摘要。最終斷網 probe 13 個檢查、真實 runner 23 個檢查、獨立核對 34 個檢查通過。
- 真實有效 turn：A 初次約 21.55 秒、B 約 26.44 秒、A 接續約 15.32 秒；不存在模型約 3.56 秒即失敗。沒有自行重跑真實模型案例。
- 已回報用量合計 **154,644 tokens**，其中 input 153,480（含 cached input 112,000）、output 1,164。`tokenUsage.total` 按 thread 累計；A 接續後的 91,261 加 B 的 63,383，沒有再重複加 A 初次用量。不存在模型未回報用量，不能宣稱為零成本。
- 本機認證來源 hash 不變；A worker 沒有 auth.json，A／B stderr 與模型事件未找到已知秘密。沿用 A 組的外部短效 token 模式，不進行真實刷新。
- 執行後 B 組 Docker label 查無容器，`.runtime/` 無殘留工作；未修改 A 組，未 push／PR／部署。

以上為小型合成案例，不推廣成大型 skill 清單截斷、所有插件／admin 來源、任意語意衝突、全工具白名單或跨版本可靠性的證明。相關官方介面說明集中在 [操作說明](README.md)，本結果以保存的固定版本證據為準。
