# E 組結果：真實專案整合與執行追蹤

執行日期：2026-09-10。**E0–E5 通過；E6 為 inconclusive：取消命令缺少完成事件。** 本批實際派發 7 次 `turn/start`，未使用剩餘 3 次預留配額。這是單主機、固定版本、單一真實 repo 副本的整合證據，不是正式產品或跨版本可靠性驗收。

契約與操作方式見 [README](README.md)；機器結論見 live/report.json（本機證據：`results/live/report.json`），主要動作見離線時間線（本機證據：`results/live/timeline.md`），完整性與用量核算見 audit.json（本機證據：`results/live/audit.json`）。

## 各項結論

| 項目 | 結果 | 主要證據與界線 |
| --- | --- | --- |
| E0 環境基準 | pass | 修正後 E0（本機證據：`results/e0-corrected/report.json`）：`npm ci`、check、30 個原始測試、完整 local Tina＋Astro build 均通過，輸出 9 個頁面。固定來源與 113 個追蹤檔案未變。 |
| E1 真實閉環 | pass | 真實 coding 只修改 `news.ts` 並新增 `news-date.test.ts`；獨立驗證（本機證據：`results/live/verify-main/report.json`）通過原 repo check／79 個測試、45 個固定驗收與完整 build。非法文章 build 失敗且指出 `e-invalid-date.mdx`。fresh review（本機證據：`results/live/b0e9fbd2d68eb926/response.json`）通過；未採納至 active、未授權發布。 |
| E2 回答與 resume | pass | 模型提問（本機證據：`results/live/93a14eaee3fb376c/response.json`）後停止原容器／app-server。普通留言與錯誤問題綁定均未派發；合成明確回答綁定問題 hash、revision 0 與固定 commit 後產生 revision 1。新 app-server resume（本機證據：`results/live/9b002ff0fb56f0b0/thread.json`）保留同 thread，實際完成後續 coding。 |
| E3 執行中恢復 | pass | 真正退出 LangGraph host：一次在 coding 命令已開始，一次在結果已保存但尚未收取。新程序恢復後同 container／thread／turn，coding 只有 1 筆派發、1 次結果收取；舊 attempt 通知不推進 review。身分與注入點在 attempts.sqlite（本機證據：`results/live/attempts.sqlite`）及時間線。 |
| E4 有界修正 | pass | 刻意注入（本機證據：`results/live/e4-injection.json`）使合法閏日失敗，固定驗收（本機證據：`results/live/verify-injected/report.json`）先證明回歸。只派發一次 repair 及一次 fresh review；修正驗證（本機證據：`results/live/verify-repair/report.json`）通過，E4 結果（本機證據：`results/live/e4.json`）保存新 commit 與新證據。不是模型自然失誤。 |
| E5 取消與並行 | pass | E5 證據（本機證據：`results/live/e5.json`）：兩個真實 turn 同時停在 lab barrier；目標 `turn/interrupt` 回覆 `{}`，終止事件為 `interrupted`，容器另行確認停止。另一工作在取消後仍寫入進度並完成，保留目標部分成果；重啟 host 後遲到通知未重新派發。 |
| E6 可追蹤性 | inconclusive | 保存 1,384 筆 worker 事件、host SQLite 事件與離線時間線；worker 移除後兩個交付 bundle 均可重建，配置、命令、候選、驗收與用量可核對。但取消目標的 `commandExecution` 只有 started，沒有 completed，無法宣稱完整命令生命週期。缺口已明確標示，沒有用容器停止補造事件。 |

原始候選 `7bdd3c9266d64af75187007f0f43229987b0f458` 與修正候選 `11b6527ea9660034684e2c3577fef7f5de7fb87b` 的 tree 相同。新 commit 仍重新執行全部驗證及 fresh review，沒有沿用舊 commit 證據。成果是 lab bundle；active repo 沒有套用這些變更。

## 環境與實際生效

- 固定來源：`brand-frontend@506158ab49b672dc8e86604d8f1f4dca28a9b340`；完整 44 個可達 commits。baseline manifest（本機證據：`results/e0/baseline.json`）核對 commit、tree、檔案 hash 與歷史，沒有 alternates、object hardlink、外部連結或 remote。
- Node `22.22.0`、Codex `0.153.4`、`gpt-6-astra`／`low`；E image ID 為 `sha256:a2e914b980255bc3ceceb37fc1c06384447246e8735ed7dc8412aec0c71bea7e`。這是本地 image content ID，沒有 registry RepoDigest。
- Python `3.11.15`；沿用 D 的鎖定環境：LangGraph `1.2.11`、checkpoint `4.2.0`、SQLite checkpointer `3.1.1`。未修改 A–D 的程式或歷史結果。
- 配置預檢（本機證據：`results/live/93a14eaee3fb376c-preflight.json`）顯示 `/codex-home/AGENTS.md` 與 `/work/AGENTS.md` 為原生指引來源，模型／推理設定正確，lab skill 可發現。真實提問事件（本機證據：`results/live/93a14eaee3fb376c/events.jsonl`）包含讀取 skill 與執行 inspect；coding 也實際使用 skill test。
- 無模型配置／連線探測（本機證據：`results/probe-configured/report.json`）確認每次 host client 退出後 app-server 仍由容器 adapter 持有。單純關閉 stdin 後一秒內仍存活，需明確停止；停止後可啟動新 app-server。此探測本身不等於模型 session resume，後者由 E2 另證明。
- 普通驗證斷網，fixture 在同容器的 `127.0.0.1:4177`；未帶 TinaCloud 設定。模型容器需對外連 OpenAI，沒有網路目的地白名單。6 GiB 容器／4 GiB Node heap 可完成這次 build；cgroup peak 到達 6 GiB（包含快取等記憶體），不能據此承諾還有資源餘裕或適合並行 build。

## 失敗、修正與合成證據

保留實際失敗，不把歷史結果改成通過：

1. 首輪 E0（本機證據：`results/e0/report.json`）：lab 將 build 變數注入單元測試，導致兩個「缺少變數」測試失敗。依原 CI 修正為僅 build 注入，沒有修改產品測試。
2. 第二輪 E0（本機證據：`results/e0-validated/report.json`）：複製套件時 symlink 被轉成 image 路徑，且 Tina 達 Node heap 上限。lab 改為保留相對 symlink、調整已量測的記憶體限制後通過；未改 lockfile 或放寬容器權限。
3. 主線 preflight 失敗（本機證據：`results/live/host-error.log`）：配置 hash 遞迴掃到正在刪除的 session 暫存。限縮為固定配置與 skills 來源；以 host 無 dispatch ledger、adapter 無 dispatch intent／turn 事件、舊容器已移除三項證據，重新準備尚未派發的 coding。保留原提問、已接受回答與 session，沒有重跑模型提問。
4. 固定驗收自我檢查（本機證據：`results/acceptance-validated/report.json`）：未修改 baseline 在 45 個案例中 29 個失敗，證明驗收會抓出原日期缺陷。早期報告總數誤寫 44 已記錄更正；未更改案例或預期。

`test_flow.py` 的 6 個無模型測試涵蓋未綁定回答、舊通知、停止不明、容器不明不重送、跨程序修正上限、舊 test／review 拒用。`test_trace.mjs` 涵蓋跨 delta 假秘密、組合後去秘密、保留文字相同的 delta、generation 接續序號及排除完整推理內容。這些屬替身／合成測試，不冒充真實 OAuth 刷新、真實失敗 retry 或完整存取審計。

## Token 用量

| 回合 | input | cached input（已含於 input） | output | 已知 total |
| --- | ---: | ---: | ---: | ---: |
| 提問 | 49,468 | 27,776 | 437 | 49,905 |
| coding／resume | 145,773 | 138,496 | 2,393 | 148,166 |
| fresh review | 86,877 | 54,016 | 504 | 87,381 |
| repair | 235,031 | 206,208 | 940 | 235,971 |
| repair fresh review | 83,379 | 54,656 | 724 | 84,103 |
| 並行 A／取消（partial） | 27,789 | 0 | 182 | 27,971 |
| 並行 B／完成 | 70,641 | 55,552 | 276 | 70,917 |
| **已知合計，非完整批次總量** | **698,958** | **536,704** | **5,456** | **704,414** |

固定版本在新 app-server resume 後，用量 counter 從該 generation 的請求重新累計，不能以相同 thread ID 直接減去提問回合總數。離線核算逐一檢查每個回報的 `last` 加總與該 generation 的最終 `total` 相等後才合計；cached input 不再相加。取消回合保留取消前已知值並標 partial，不補零、不宣稱完整，也不換算金額。原始額外欄位仍保留於事件／usage 檔。

## 尚未證明

E6 仍缺取消命令的完成事件；一般命令紀錄不等於所有檔案存取審計。模型沒有提供推理摘要時記為 unavailable，不是通過條件。未驗證 A 的真實 OAuth 刷新、跨主機 session 遷移、其他 repo／版本、正式 UI、發布或正式產品架構。完成、交付與採納分開：候選已交付並 review 通過，`adopted=false`；沒有 push、PR 或部署。

完成後已清理 E 專用容器、fixture、session 與套件 runtime；保留唯讀完整 baseline、固定 image、程式與去秘密成果。清理後的離線 audit 不依賴 worker checkout 或 session。
