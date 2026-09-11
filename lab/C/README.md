# C 組實驗：成果、回答與 review 交接

契約：[C1–C5](../../docs/experiments/c-handoffs.md)。結果主要維護於 [RESULTS.md](RESULTS.md)。這是 Python 標準函式庫的單主機實驗，沒有產品服務、UI、LangGraph 或外部發布。

## 重跑

從專案根目錄執行，使用 Python 3.11 以上、Git、Docker 與 Codex 0.153.4：

```sh
# 真實子程序與 Git 的模擬測試；不連模型。
python3 lab/C/test_lab.py

# 由本機固定 Codex 版本產生 schema；不連模型。
python3 lab/C/contract.py

# 重用 A 組映像；尚未建立時才執行。
docker build --pull=false -t agent-workbench-lab-a:0.153.4 lab/A

# 使用本機已登入的訂閱認證；results 下的 run 名稱不可重複。
python3 lab/C/runner.py \
  --auth-file /absolute/path/to/auth.json \
  --model gpt-6-astra --seconds 120 --run live-next

# 不使用模型；重新核對證據、重建 bundle 與重播回答／證據判斷。
python3 lab/C/verify.py lab/C/results/live-next

# 已保存有效 coding 候選時，只重新 review；最多一個模型 turn。
python3 lab/C/runner.py \
  --auth-file /absolute/path/to/auth.json \
  --reuse live-corrected --run review-next
```

每次最多三個模型 turn，依序為必要問題、回答後 coding、fresh review；每回合最多 120 秒。這是回合與時間上限，沒有 token／金額硬上限。省略 `--model` 時，從首次 `model/list` 選預設模型並固定三回合使用；reasoning effort 為 `low`，不允許模型 fallback。超時會要求 interrupt 並移除該容器，不自行重跑。

## 實驗材料與責任

| 檔案 | 責任 |
| --- | --- |
| [core.py](core.py) | 成果收取、Git bundle 與重建、候選證據比對、明確回答接續。 |
| [fixtures.py](fixtures.py) | 合成標籤正規化需求、結果格式及獨立 Node.js 驗收程式。 |
| [test_lab.py](test_lab.py) | C1 的缺失／錯誤／部分成果，C2 重建，C4 舊證據，C5 留言／回答及新程序讀取。 |
| [contract.py](contract.py) | 固定 Codex 的結構化輸出、thread start/resume、interrupt 介面摘要。 |
| [runner.py](runner.py) | 真實三回合、容器移除、成果匯出、重建、fresh review 與新候選測試。 |
| [verify.py](verify.py) | 從保存證據獨立核對，不以 runner 的 passed 欄位單獨判定通過。 |

合成工具 `normalizeTags` 必須 trim、小寫、去重、排序、不修改輸入並拒絕錯誤型別；空標籤的處理刻意留作必要問題。測試程式扮演使用者，先留言，再送綁定問題、需求雜湊與基準候選的 `answer_and_continue: discard`。這不是 I-Fan 對真實產品作出的決策，也沒有實作 UI 或真人回答端點。

第一個 worker 提問、保存摘要後移除。第二個 worker 嘗試以明確 ID resume，確認 session 不存在後，僅使用保存交接與回答建立新 thread。它修改 `tags.cjs`、新增 `usage.md`；普通程式執行固定驗收並建立 commit，再匯出完整 Git bundle。開發工作目錄與 Codex home 都在 tmpfs，容器移除後不能靠原目錄重建。

Fresh review 使用第三個容器、新 Codex home 與新 thread。輸入只有固定候選、需求、驗證紀錄及驗收程式；完整候選 repo 唯讀掛載，不提供開發對話或 session 檔。模型 review 使用一般 `thread/start`＋結構化 `turn/start`，沒有宣稱驗證專用 `review/start` 接口。

需求綁定使用 `json.dumps(value, sort_keys=True, ensure_ascii=False).encode()` 的 SHA-256；新執行與 review 輸入直接寫入這些位元組、不加換行，所以需求檔本身的雜湊等於紀錄。`--reuse` 保留先前原始輸入與來源雜湊，僅將新 review 的需求檔統一格式，需求內容與候選不變。`usage_total` 是本條交接鏈三回合的合計；`usage_this_run` 排除沿用的回合，跨執行加總不可重複計入。

最後由普通程式對說明文件建立新 commit，實際重跑測試，確認舊測試／review 都不能直接替新版背書；新版測試通過也仍缺新版 review。這個修正版是 C4 的故意未放行材料，沒有再花模型額度 review，也沒有自動採納任何候選。

## 保存與邊界

- `results/<run>/` 保存問題、回答、需求、部分產物、兩份完整候選 bundle、測試與 review、生命週期、用量與來源雜湊。首輪失敗證據保留，重跑不覆寫既有 run。
- `partial-artifacts/` 在 commit／bundle 前保存指定程式與新增說明。它不是可交付 Git 候選；仍須完整 bundle、版本及驗證。主機突然中止、尚未匯出的編輯不保證保留。
- 沿用 [A 組認證讀取與 RPC](../A/README.md)：只讀本機登入，access token 經 stdin 注入；不複製 auth.json，不交出 refresh token，不掛日常 Codex 目錄、不刷新或改用 API。
- 容器非 root、唯讀根目錄、移除 capabilities、不掛 Docker socket。模型 turn 用 `externalSandbox`，隔離由 Docker 掛載負責；驗收容器完全斷網。模型容器可連線，未實作目的地白名單。
- 只保存合成任務的模型結構化成果；原始 RPC 與 stderr 不落一般紀錄。事件與匯出檔掃描本次已知認證值。這是已知值檢查，不能視作通用秘密偵測平台。
- 實驗中的 Docker 後端無法透過 `docker cp` 匯出 tmpfs bundle；實作使用容器內 `cat` 的 stdout 位元組串流，避免依賴此行為。
- `.runtime/` 可刪除；正常結束清理臨時目錄與容器。主機強制中止時可用 `docker ps -a --filter label=agent-workbench.lab=C` 查找本組容器，再核對名稱處理。
- 目前工作目錄不是 Git repository；本實驗僅在臨時合成 repo 建立 commit，沒有對專案執行 commit、push 或 PR。

[官方 app-server lifecycle](https://learn.chatgpt.com/docs/app-server#lifecycle-overview) 描述 thread start/resume 與 turn 結束通知；固定版本的 `outputSchema` 介面另由 contract.json（本機證據：`results/contract.json`） 查核。結構化輸出與回合完成不等於語意正確，實驗用普通程式驗收及獨立 review 分開判斷。
