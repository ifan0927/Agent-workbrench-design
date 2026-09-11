# D 組驗證結果

驗證日期：2026-09-10。**D1–D4 的指定最小實驗通過**，實作與重跑方式見 [README.md](README.md)。D4 依使用者本次確認，採 `lab/D` 的合成 repo；結論限於這個單主機切片，不代表產品架構已定案。

## 環境及證據

Python **3.11.15**、LangGraph **1.2.11**、langgraph-checkpoint **4.2.0**、SQLite checkpointer **3.1.1**；完整依賴固定於 [uv.lock](uv.lock)。Docker client／server **28.5.2**，使用本機 Docker 端點與已有的 `node:22.22.0-bookworm` image；實際 image ID 保存在報告。

| 證據 | 實際結果 |
| --- | --- |
| 負向測試（本機證據：`results/tests.json`） | 6／6 通過；Docker 回應為替身，驗證失聯、身分不符、結果錯誤與停止不明等處理。 |
| 完整執行報告（本機證據：`results/validated/report.json`） | 31／31 通過；真實 LangGraph、SQLite、host 子程序退出及 Docker 操作，包含 D4 總閘。 |
| D4 環境報告（本機證據：`results/validated/environment.json`） | 13／13 通過；兩個獨立 checkout、services、並行 build/test、資料／port 與清理。 |
| 離線稽核（本機證據：`results/validated/audit.json`） | 36／36 通過；重新讀原始成果、實際啟動筆數、持久化 checkpoint、fixture bundle 與來源 hash。 |
| 程式來源 manifest（本機證據：`results/validated/source-manifest.json`） | 稽核時與目前實作相符；不把舊程式執行結果當成新程式證據。 |

上述檢查有包含關係，不合計成獨立案例數。`test_lab.py` 是模擬；完整執行使用真實容器與流程引擎，但 worker 的「模型工作」、人工回答與中斷時機是固定替身／測試輸入。**模型呼叫 0 次，未讀取本機認證，沒有訂閱或 API 模型用量。** 人工只確認 D4 目標；未測量產品操作成本或人工接手時間。

## 逐項結論

| ID | 結論與觀測 | 邊界／架構意義 |
| --- | --- | --- |
| D1 | 通過。每次 start／status／resume／recover 都是新的 OS 程序；等待 worker 與等待回答後，從同一 SQLite checkpoint 恢復。普通留言與錯誤回答不派發，明確回答後進入第二個 attempt，最後完成。 | `flow.py` 持有全部下一步規則；runner 沒有整件工作重試或另一套 controller。本切片支持繼續評估 LangGraph。 |
| D2 | 通過。分別在 create 前、啟動意圖落盤後、create 後、start 前後，以 `os._exit(86)` 中止 host。可核對的容器沿用同一 ID；重送同一 attempt、兩程序同時 start 及已退出後 ensure 都沒有新增工作入口紀錄。 | 啟動意圖已保存但找不到容器時，進入 `interrupted`，實際啟動 0 次；已啟動後被移除也不重開。這犧牲不明狀態的自動恢復，以避免重複副作用。 |
| D2：遲到結果 | 第一個 attempt 的通知送入第二個 attempt 時被拒絕，仍等候第二個工作。已完成／已取消工作的重複通知不推進流程。 | 通知中的結果不被採信；收集時核對落盤結果的 attempt 與成功退出狀態，原始成果可保留。 |
| D3 | 通過。Docker top 先確認父子程序；兩者忽略 TERM。保存取消後中止 host，再恢復並停止目標容器；目標 heartbeat 停止，另一 worker 仍在執行且 heartbeat 增加。部分成果仍在。 | 取消前後重啟皆可核對；停止後再次重啟不重新派發。容器已消失時明確回報 `cancel_unknown`，不把停止要求當成停止證明。 |
| D4 | 通過。固定 commit `b8c48966d9733da895e817237cdca730c93e65ae`，保存 fixture.bundle（本機證據：`results/validated/environment/fixture.bundle`）。image build 成功，兩個 worker 各自 build 並通過 2 項 Node tests；執行時間重疊。 | 兩個獨立 bridge network／checkout／資料目錄；localhost ports 為 32768、32769。同時向各自服務的同一 key 寫入不同資料後正確讀回，驗證服務 DNS、HTTP 及資料隔離。 |
| 清理 | 執行報告確認容器、網路及 runtime 目錄移除；完成後再以 Docker label 查詢，D 組容器／網路與本次 D4 image 均無殘留。 | 成果、checkpoint 與 Git bundle 先保存於 `results/validated`，再清理執行資源。 |

D4 原始輸出：image build（本機證據：`results/validated/environment/build.txt`）、worker 0 tests（本機證據：`results/validated/environment/test-0.txt`）、worker 1 tests（本機證據：`results/validated/environment/test-1.txt`）。兩個 worker 在 barrier 均已存活並完成寫入，放行後各自讀回 `dataset-0`、`dataset-1`，避免僅以「不同目錄名稱」推論隔離成功。

## 首輪失敗與修正

首輪報告（本機證據：`results/validation/report.json`）的 D1–D3 檢查通過，但 D4 讀取 host port mapping 時遇到 `KeyError: '8080/tcp'`，整輪判定失敗。獨立探測確認此主機使用 `--internal` network 時，容器雖執行中且 HostConfig 有 publish 設定，NetworkSettings.Ports 仍為空。

修正為每個工作專屬的一般 bridge network 與動態 `127.0.0.1` port，重新完整執行並通過。舊結果保留其舊來源 manifest；主要驗收證據是 `results/validated`。不將此本機觀測推廣為所有 Docker 版本的通則。

## 未驗證與採用邊界

- 沒有接入真實 Codex 模型；D1–D3 的工作輸出是替身。訂閱登入與認證另看 [A 組結果](../A/RESULTS.md)，本次不改變其結論。
- D4 只驗證已指定的合成 Node repo 與 HTTP 測試服務，不代表其他專案、資料庫、私有套件、外部網路依賴或部署環境可用。
- 中斷是 host 子程序退出，不包含 Docker daemon 重啟、主機斷電、磁碟毀損、多主機／網路磁碟，亦不提供跨系統 exactly-once 保證。
- 沒有 UI、長駐事件通知服務、完整 retry／repair 產品流程、OAuth 刷新、GitHub push／PR 或部署。一般 bridge 可出網；未驗證網路出口白名單或多租戶隔離。

本次證據支持「LangGraph 作唯一外層流程、runner 管可核對的執行副作用」繼續收斂。SQLite＋本地檔案鎖只作單主機驗證；遇到啟停事實不明時保留證據並交回接手，不以 checkpoint 取代外部狀態查核。
