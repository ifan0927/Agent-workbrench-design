# E 組實驗設計：真實專案整合與執行追蹤

設計與執行日期：2026-09-10。**已獲授權開始實作與執行；使用者另明確確認可使用本機登入及將相關任務／原始碼傳送至 OpenAI。** 本文件維護 E0–E6 契約與操作方式；實際結論與限制以 [RESULTS.md](RESULTS.md) 為主。實驗入口見 [docs/experiments](../../docs/experiments/README.md)。

使用者已確認：以實驗為基準，後續工作留在 `lab/`；使用 active repo 的完整獨立副本供任意實驗修改；模型用量只記 token；觀察外部配置是否生效及 agent 的可見執行過程。先前僅設計的授權已由本次「開始進行 E 組實驗」及上述登入／傳送確認更新；不包含 push、PR、部署或日常登入刷新。

## 1. 要證明什麼

在固定版本、單主機及一個真實專案副本上，驗證：外部組裝的環境與配置確實被載入、相關能力被正確使用；Codex 自主完成有界工作；平台能等待回答、恢復觀察、收取可重建成果、獨立 review、有限修正及取消，並留下可查核的執行軌跡。

| 層次 | 主要證據 | 不能推論的事情 |
| --- | --- | --- |
| 組裝正確 | repo commit、配置與 skills 全目錄 hash、image、掛載、工作目錄、工具宣告 | 檔案存在不等於 Codex 已載入。 |
| 原生生效 | 指引來源、skills 發現、有效模型／推理設定、必要工具狀態 | 接口接受設定不等於設定受支援。 |
| 實際使用 | 搜尋／讀檔、skill script、工具回呼及其執行結果 | 命令證據不是完整檔案存取審計；不要求用完所有 skills。 |
| 行為符合 | 固定驗收、實際 diff、產物、獨立 review 與負向案例 | agent 自述與推理摘要不能單獨證明遵循或因果。 |

通過只支持這個整合切片的可行性，不等於正式產品、所有 repo、跨版本／跨主機可靠性或模型品質已驗收。真實 OAuth 刷新仍沿用 [A 組後續計畫](../A/README.md#後續真實認證生命週期規劃未執行)，不混入 E 組通過聲明。

## 2. 審核結論與既有實驗的銜接

下表保留從 A–D 帶入 E 的待補接縫；本次是否成立以 RESULTS.md 為準，不回寫 A–D 的歷史結果：

| 來源 | 可沿用的材料 | E 組必須補的部分 |
| --- | --- | --- |
| [A 組](../A/RESULTS.md) | 短效 token 注入、固定 Codex image、雙 worker、秘密與刷新模擬 | A 的 host 直接持有 stdio；host 重啟後的真實連線生命週期尚未成立。 |
| [B 組](../B/RESULTS.md) | 完整配置快照、發現／預檢、動態工具與行為核對 | 在真實 repo 使用相同邊界，不能只重現合成 receipt。 |
| [C 組](../C/RESULTS.md) | bundle 重建、固定需求、fresh review、回答與舊證據拒用 | 原實作使用 ephemeral thread；成功 resume 要另設保存路徑，不能只更換 thread ID。 |
| [D 組](../D/RESULTS.md) | LangGraph 唯一外層決策、attempt、SQLite、啟停核對 | 將固定 worker 替身接成真實 Codex；分開核對原生 turn 中斷與容器停止。 |

盡量引用／重用現有模組，E 專用轉接與觀測留在本組。不為套入 E 默默改寫 A–D 的歷史結果；若共享實作確需變更，記錄來源版本及重跑直接受影響的檢查。

## 3. 真實 repo 與副本

首選 `~/Developer/active/brand-frontend`（公開版代稱，可用 `LAB_E_SOURCE` 指定實際路徑）。2026-09-10 唯讀查核：工作樹乾淨，HEAD 為 `506158ab49b672dc8e86604d8f1f4dca28a9b340`；113 個追蹤檔案約 6.2 MB，未見 tracked symlink、submodule 或 `.gitattributes`。這是查核時的候選基準，不宣稱環境已跑通。

採用理由：有 Astro／TypeScript、Vitest、內容資產與真實 build；repo 自有 API fixture，可避免連真實 backend；Tina build 支援 local mode。`admin-frontend` 當時有未提交修改並依賴兄弟 repo 契約；`backend` 需要較多服務。文件型 repo 與已封存 ALC 不作本輪修改目標。

每次執行前只需在來源 repo 核對：`AGENTS.md`、`package.json`／lockfile、`docs/.rules/testing.md`、`.github/workflows/pr-ci.yml`、`scripts/tina-build.mjs`、`scripts/brand-api-fixture.mjs`，以及任務涉及的 `src/lib/content/news.ts`／`news.test.ts`。原 repo 的既有規則跟隨副本；本實驗不修改正式產品、不 push／PR／部署，不能因副本內有發布指引就擴張範圍。

完整副本的準備契約（本次已執行）：

1. 先重新核對來源 HEAD 與工作樹。預設仍使用上述固定 commit；若有新修改，保留原處、不自動納入。固定 commit 不可取得時回報缺口，不默換版本。
2. 建立獨立 Git clone，包含基準全部追蹤檔案、資產、文件、lockfile 及完整可達 Git 歷史；核對 commit、tree、檔案 hash 與歷史完整性。拒絕未處理的 shallow／partial clone、缺物件或外部檔案連結。
3. 不使用指向 active 的 worktree、symlink、Git alternates 或共享 object hardlink。基準副本唯讀保存；每個 worker 取得實驗區內的完整可寫副本。worker 不掛載 active 目錄。
4. 不搬日常 `.env`、認證、Git hooks、本機 Git config、`node_modules`、生成檔及暫存；依 lockfile 在實驗 image 準備依賴。移除副本的 remote／push 連線，不配置 GitHub／TinaCloud／部署憑證。
5. 記錄來源與複製規格；來源副本準備前後核對 HEAD、工作樹及來源檔案 hash。測試寫入只發生在 lab 的 worker 副本，不能以工作樹乾淨取代實際隔離檢查。

這是本輪本地取樣的例外，不把[產品的遠端 repo 基準](../../docs/product.md)改成本機 checkout 同步。本次實作沿用以下路徑；受限 session 與套件暫存只放在 `.runtime/`，完成採證後清理：

```text
lab/E/
  README.md
  inputs/       固定需求、配置／skills、回答事件及普通程式驗收
  baseline/     完整獨立專案基準；模型不可改
  .runtime/     各 attempt 的可寫副本與暫存 session
  results/      去秘密事件、manifest、bundle、測試／review 與用量
```

## 4. 任務與環境基準

任務候選為「消息日期有效性與來源錯誤診斷」。目前 `formatNewsDate` 有日期／ISO 輸入測試，`getNewsPosts` 經 frontmatter 讀入文章，適合驗證少量程式變更、行為測試及實際靜態 build。這是實驗限定契約，沒有授權變更正式產品規則。

本次已在任何模型執行前固定 [task-r0.json](inputs/task-r0.json) 與 [acceptance.test.ts](inputs/acceptance.test.ts)：接受的日期與 ISO 字串文法、曆日／閏年規則、是否保留既有寬鬆輸入、輸出格式與時區語意、錯誤包含的來源資訊。至少包含正常日期、既有 ISO 範例、合法閏日、非法月／日、非閏年 2 月 29 日、空值／垃圾輸入及有效文章 build。不可只寫「支援 ISO」而留下無界解讀。

E2 唯一刻意未決的工作決策是：無效文章要略過，或阻擋 build。建議測試回答採「阻擋 build 並指出來源檔」；回答前只允許探索與提問，不允許自行採納預設。Controller 保存的預定回答及完整測試不可提前交給該提問回合；回答後更新需求版本與驗收綁定，才交給 coding／review。

| 準備項目 | 設計要求 |
| --- | --- |
| 原始環境 | 先對未修改副本執行 `npm ci`、`npm run check`、`npm test`、`npm run build`；以實際容器結果判斷，不沿用主機 `node_modules`。 |
| 依賴與資源 | 優先沿用 Node 22.22.0、Codex 0.153.4 及 D 的固定流程依賴；以 lockfile 建立專用 image 並記錄 digest。E0 量測建置需要的磁碟／記憶體，不直接沿用 C 的 64 MB 工作 tmpfs 或 A 的 1 GB 限制。套件下載僅為 setup 階段；不暗改 lockfile 修環境。 |
| 本地 API | `SITE_URL=https://example.com`，`BRAND_API_BASE_URL` 指向該次驗證的本地 fixture；不提供 `TINA_BRANCH`／`TINA_CLIENT_ID`／`TINA_TOKEN`，使用 local build。fixture 目前只 listen `127.0.0.1`，第一版與 build 同容器，避免誤認兄弟容器可直接連入。 |
| 並行環境 | 每工作獨立 checkout、build 產物、fixture 與 session；不發布固定 host port。相同容器內部 port 不共用網路 namespace；清理按本組 label 與實際身分執行。 |
| 有效配置 | 共用約定、原 repo 指引、模式、任務與一項相關 lab skill 使用 B 的快照方法；skill 提供本輪驗證入口／fixture 使用方法與腳本。記錄發現、讀取、腳本結果，不能用回報版本字串取代實際使用。 |
| 固定驗收 | 任務行為驗收與原始驗證命令保存在模型不可改的輸入；coding 可新增測試，但不能改普通程式的通過標準。核對既有測試／scripts／lockfile 未被刪除或弱化；驗收程式失敗應停止並修正實驗程式，不修改預期把失敗洗成通過。 |

有效內容的基準 build 與放入非法文章後預期失敗的 build 是不同檢查。負向文章只放在獨立驗證副本，保存檔名／hash／退出結果，不污染交付候選。原始基準已失敗時，先分類環境／原有問題，不能把它交給模型順便修好再宣稱 E0 通過。

## 5. E0–E6 通過條件

| ID | 做法 | 通過條件與證據界線 |
| --- | --- | --- |
| E0 環境基準 | 完整副本、依賴 image、本地 fixture 與原 repo gates | 未改程式前 check／test／完整 Tina＋Astro build 通過；來源未被修改；保存有效環境、命令、退出碼及必要輸出。只跑 `build:astro` 不能替代完整 build。 |
| E1 真實閉環 | LangGraph 派發真實 coding，按固定配置執行，收取候選，由普通程式驗證，再 fresh review | 組裝→原生生效→相關能力使用→產物均可核對。候選可在移除 worker 後從 bundle 重建並驗證；review 新容器／home／thread，只讀完整候選、需求與測試，不承接開發對話。完成、交付、採納、下一步授權分開保存。 |
| E2 回答與 resume | 真實模型提出必要問題，保存後退出 app-server；流程 host 亦重啟。先送普通留言／錯誤綁定，再送明確回答 | 前兩者不派發；回答綁定問題、需求版本與候選／基準，才形成新 attempt。保留相容 session 的成功 `thread/resume` 需有實際回覆及後續 turn，沿用同 thread；不能只在活著的 app-server 上再呼叫 turn。回答為合成事件，非真人 UI 驗收。 |
| E3 執行中恢復 | 在真實 coding 已確認開始後及結果已保存但流程尚未收取時，中止流程 host，重啟並重送同 attempt 通知 | 可核對時沿用同 worker／thread／turn；入口及 `turn/start` 派發紀錄沒有增加，結果只收取一次，關鍵事件持續保存。不明時不得重送模型工作；保存 `interrupted` 與缺口。安全停止可證明失敗處理，但不能算成功持續執行。 |
| E4 有界修正 | 從合格候選產生明確標示的實驗錯誤 commit，固定驗收先證明失敗，再給一次模型修正及 fresh review | 新 commit 拒用舊 test／review；修正產生新候選並重新綁定全部證據。超額與重複失敗的停止規則可用替身驗證，不能算真實模型已測。注入錯誤不冒充模型自然失誤。 |
| E5 取消與並行 | 兩個真實 turn 重疊時取消目標。以已觀察的命令／lab barrier 定位時機，先 `turn/interrupt`，再依期限停止容器 | 分別記錄原生中斷回覆／終止事件與容器停止證明。另一 turn 在取消後仍有進度且完成；兩者不串用檔案、fixture 或結果。原生中斷失敗而容器停止成功，須分別報告，不能宣稱原生取消通過。取消後重啟、遲到結果不能重新派發；部分成果保留。 |
| E6 可追蹤性 | 共用所有案例的事件收集與離線查核，不增加專用模型 turn | worker 移除後可重建主要動作與狀態順序，對照配置、工具、diff、驗收及用量；host 重啟後有持久化接續／去重與缺口標示；模型自述、工具事實、host 判斷可區分。完整性規則見下一節。 |

E1／E2／E3 共用提問→回答→coding→review 主線。E4 沿用其候選，不重做整條工作；E5 另用可控的兩個小型真實工作。E1–E6 各自保存 pass／fail／not-run／inconclusive 及證據層級，不因其他案例成功而補成通過。

### E2／E3 的連線與 session 接縫

現有 [A rpc.py](../A/rpc.py)與 [Dockerfile](../A/Dockerfile)使用 host 持有的 stdio 管線；B／C 沿用，且 C 為 ephemeral thread。D 的獨立替身容器成功恢復，不能證明這個連線也能恢復。

本次先用無模型探測確認 host 退出、stdin 關閉及 app-server 退出的行為，再採容器內薄 worker adapter 持有 stdio 連線與事件保存；未比較其他 transport，不假設重連會重播遺失事件。薄 adapter 不決定下一步、不自動重送 turn、不掌管整件工作 retry／repair。

E3 中止的是 LangGraph 操作程序；負責 RPC 與事件保存的邊界必須明確，不能測試時偷偷保留同一 host 記憶體卻稱平台已恢復。啟動意圖、已取得的 thread／turn ID、結果保存與已收取狀態要落盤；發送成功但回覆／ID 不明時先查核，不能以同一輸入自動重送。微觀中斷點與不明分支沿用 D 的替身測試，不耗模型逐點重跑。

同時說明動態工具／認證回呼由誰回覆，host 離線時是可繼續服務、有界等待或明確失敗；不能只保存輸出卻遺漏 server request。E3 的中斷點需有可觀察的進度與恢復後結果，不以未執行工具的空 turn 取代真實工作。

E2 則是在回合結束後保存相容 session，關閉原 app-server，再啟動新 app-server，以原 thread ID 恢復並注入已綁定回答。session 設定不能仍為 ephemeral；只保存必要 session 資料於受限 runtime，認證另外注入。換版配置或需求超出原授權時不強行 resume。session 遺失沿用 C 的交接重建路徑，另標示 fallback；成功 fallback 不冒充成功 resume，不承諾跨主機 session 遷移。

E5 的 barrier 只控制中斷時機，不限制解題步驟。停止請求先保存，再嘗試原生 interrupt；期限後以指定容器 ID 停止並核對程序。無法觀測時為 `cancel_unknown`；全機 prune、Docker daemon 重啟及主機斷電不納入。

## 6. 執行軌跡與證據完整性

觀測以工具與產物事實為主。保存 agent 自行提供的計畫、進度與可讀推理摘要，有助於解釋行為；不要求額外輸出完整思考、不擷取隱藏內部推理，不以敘述長度或是否提供摘要作通過條件。摘要不是完整推理或指引影響的因果證明。

2026-09-10 查閱的[官方 app-server 事件文件](https://learn.chatgpt.com/docs/app-server#events)提供 `item/started`／`item/completed`、`commandExecution`、`fileChange`、工具事件、訊息與計畫，以及 `item/reasoning/summaryTextDelta`。接口文件只作設計依據；固定 Codex／模型實際發出的種類與欄位仍需 E 組探測。不要用 `turn` 的空 items 陣列推論沒有工具工作。

| 保存內容 | 最小要求 |
| --- | --- |
| 身分與順序 | 工作／attempt／thread／turn／item ID、收集者 generation、持久化序號與時間；跨程序不可只比較各自 monotonic clock。 |
| 事件來源 | 分開標示 app-server 事件、agent 自述、host 觀測、驗證程式結果與實驗注入。提問／回答／取消／採納亦保留明確操作身分。 |
| 執行行為 | 去秘密的命令、cwd、工具名與必要參數、成功／失敗、退出碼、必要輸出；相對路徑依 cwd 解讀。只有 hash 不足以回看真實任務。 |
| 檔案與成果 | 原生 fileChange／turn diff 若有則保存，但 shell 也能改檔；以實際 Git diff、未追蹤檔案、候選 tree／bundle 與普通程式核對補足，不能只靠 patch 事件。 |
| 用量 | 按[共通 token 紀錄規則](../../docs/experiments/README.md#結果紀錄與設計決定)保存；未知／部分資料不補零。 |
| 完整性 | 事件串流斷線、截斷、重連、尚未完成的 item、重新取得的最終狀態均標示；最終狀態不能虛構成遺失的逐步事件。 |

收集者先去秘密再持久化，不保存原始認證 RPC、完整環境變數、token 或任意原始 session 到一般 report。使用允許的欄位與必要輸出；大型內容以受限大小的附件或摘要保存，記錄截斷。假 token／canary 的分段輸出測試要涵蓋跨 delta 秘密，不能各段分開掃描就當作安全。

E6 的開發對話／推理摘要供事後查核，不交給 fresh reviewer；review 仍只取得固定需求、完整候選、配置約定及實際驗證紀錄。觀測不破壞 C 組的獨立 context 邊界。

重連後依持久化收集序號／既有事件身分去重；不能把文字相同的兩個 delta 當重複而刪除有效內容。`item/completed` 與實際產物用於核對最終事實；模型訊息／summary 未提供可標示 unavailable，不是失敗。關鍵命令、候選或取消事實若缺證據，E6 相應檢查不能通過；已知丟事件時最多證明缺口被偵測，不能稱完整追蹤。

先做命令列／離線時間線即可，不建立 UI、完整 observability 平台或另一個 controller。收集應與工作執行解耦，不因每個 UI 更新等待而改變 agent 的解題流程。

## 7. 執行順序、用量與停止界線

本次採用下列固定執行基準：Codex 0.153.4、`gpt-6-astra`／`low`，模型／工具預檢沿用 B；不可用就回報，不暗換版本、模型或 API。Python／LangGraph 依 D 的鎖定依賴設計，共享程式須核對相容性，不把 A–C 使用的 Python 版本當作 E 已驗證版本。

| 順序 | 內容 | 模型 turn 配額提案 |
| --- | --- | --- |
| 1 | E0；無模型連線／保存／秘密探測；固定驗收與任務卡 | 0 |
| 2 | E2 提問，E1 coding，E1 fresh review；E3 注入在同主線 | 3 |
| 3 | E4 注入後修正、重新 fresh review | 2 |
| 4 | E5 兩個小型並行工作與取消；E6 全程共用 | 2 |
| 預留 | 在同一範圍內補證據；不是自動重跑配額 | 最多 3 |

E 組整個驗證批次最多 **10 次 `turn/start` 派發**，每 turn 最多 **300 秒**；失敗、取消與發送結果不明也占配額，計數需在派發前持久化，host 重啟不重置。Codex 內部一個 turn 可有多次模型請求；此界限不是 token 硬上限。修正候選最多一個外層 repair 回合；若主線自然失敗已用掉 repair，E4 不另取得一次，應標示未執行或提出新的執行範圍。

模型只記 token，不換算金額，不要求人工耗時計量／成本收益作本輪 gate。Build／普通測試／安裝另設程序期限：本次固定 setup／image build 每步 15 分鐘、單次 check／test／build 10 分鐘、停止觀測 30 秒；這些是防止掛住的執行界限，不是效能承諾。觀測逾時不等於工作未發生，不自動重開。

沿用 A 的外部短效 token 模式時，認證來源需在執行範圍內明確；E 不刷新日常登入、不帶 refresh token 給 worker。若過期或收到刷新要求，保存現有成果並標示認證阻擋，轉由 A 的剩餘計畫處理，不重送整件工作或切 API。

依賴不足、基準失敗、固定接口不支援或權限問題，先停止依賴該條件的切片並保留證據，不以放寬容器權限、修改 active、削弱驗收或擴大到部署來補救。取消／回合逾時不回滾已保存成果。完成與失敗均先保存必要成果，再按本次身分清理容器、fixture 與 runtime；不清理原 repo 或其他組實驗。

## 8. 後續接手順序

1. 讀本文件與根目錄 AGENTS.md；依目前授權維持設計或開始實作，不把歷史 A–D 執行授權自動延伸到 E。
2. 核對第 3 節的來源與相關 repo 規則；不預讀整個 active 或全部 docs。
3. 完成具體設計：日期輸入文法／驗收矩陣、唯一未決回答、相關 lab skill、E2 session 保存、E3 transport／adapter 與事件落盤、E5 中斷觀測點、各項 deadline／資源上限。
4. 將細節直接補入本文件；模型可讀任務與 controller 專用注入規格分離。不要另建逐輪總報告、產品 scaffold 或新 repos。
5. 取得實作／執行範圍後，按第 7 節從 E0 開始；能獨立進行的 E 設計不必等待 A 真實刷新全部完成。
6. 後續結果仍以本組 `RESULTS.md` 為主要位置，機器證據按切片保存；再更新實驗入口。未執行前不建立假結果、成功數或空的結果索引。

結果報告分開列出：真實模型／真實容器、替身／合成回答／錯誤注入、未驗證項目；環境有效性、工作閉環、resume／恢復、取消、追蹤完整性各自下結論。E 全部通過也不將 A 的真實刷新、正式產品架構或其他專案適用性標成已完成。

## 9. 本次具體接線與執行入口

日期規則採嚴格 ASCII `YYYY-MM-DD` 或附 `T`、時分秒、可選 1–3 位小數及必要 `Z`／`±HH:mm` 的字串；年 0001–9999、Gregorian 閏年、時間上限 23:59:59、offset 上限 ±14:00。輸出保留輸入開頭的曆日，不做時區轉換。固定矩陣有 11 個合法、33 個非法及 1 個現有內容案例。唯一刻意未決項仍是文章處理策略；[controller.json](inputs/controller.json) 的合成回答不掛入提問容器，回答綁定後才產生 revision 1。

| 程式 | 責任 |
| --- | --- |
| [environment.py](environment.py)／[gates.mjs](gates.mjs) | mirror clone 後轉獨立工作副本、來源與歷史核對、唯讀基準、依 lockfile 建 image、E0。 |
| [adapter.mjs](adapter.mjs)／[client.mjs](client.mjs) | 容器內持有 app-server stdio；host 每次以短生命週期 client 連容器內 loopback HTTP，不發布 host port。 |
| [trace.mjs](trace.mjs) | 持久化序號、允許欄位、先組合再去秘密的 delta；不保存完整推理或原始認證 RPC。 |
| [runner.py](runner.py) | attempt／派發意圖、配置預檢、短效 token 注入、容器核對、成果收取及停止。 |
| [flow.py](flow.py)／[host.py](host.py) | LangGraph 唯一決定提問、回答、coding、普通驗證、fresh review 與取消；使用 D 鎖定的 Python 依賴及 SQLite checkpoint。 |
| [verification.py](verification.py)／[evidence.py](evidence.py) | 從 bundle 重建、固定驗收、正負向完整 build、候選／需求與 test／review 綁定。 |
| [validate.py](validate.py)／[continue_main.py](continue_main.py)／[followups.py](followups.py) | 注入 E2／E3、已證明未派發的 preflight 恢復、E4 刻意錯誤與 E5 barrier。這些入口不決定模型工作的下一步。 |
| [audit.py](audit.py) | 移除 worker 後的離線時間線、缺口、bundle 重建與 token 核算。 |

認證來源固定為 `~/.codex/auth.json`，僅在 host 記憶體擷取 access token，經私有控制連線注入；不把憑證放入 argv、環境或成果。app-server 使用 ephemeral credential store；session 使用實驗專用 home，與認證分離。外層 `.runtime/<批次>` 是 0700；其內容器可寫子目錄用於單機 UID 映射，沒有掛載 active 或日常 Codex home。E2 先停止原容器，再將同一必要 session home 掛入新容器；review 則使用全新 home／thread 及唯讀候選。

Adapter 不處理工作重試。未支援的 server request（包含真實認證刷新）明確回覆 `host_action_required`；host 離線不會留下無回覆的請求。每個 adapter 只可派發一次 turn，外層 SQLite 在發送前累計整批 10 次上限。派發結果不明不重送；只有 host／adapter 均沒有派發意圖、無 turn 事件且舊容器已移除時，才可重新準備失敗的 preflight。

Setup 每步 900 秒；check／test／build 每步 600 秒。E0 修正後使用 6 GiB 容器、4 GiB Node heap、2 CPU、512 PID、1 GiB `/tmp`；Docker 根檔案系統唯讀、非 root、移除 capabilities。模型容器需對外模型連線，普通驗證完全斷網、fixture 只在同容器 loopback。沒有出口目的地白名單，不宣稱多租戶隔離。

從專案根目錄執行（`results` 入口拒絕覆寫；先讀結果，勿重跑已完成批次）：

```sh
# 無模型檢查。
lab/D/.venv/bin/python lab/E/test_flow.py
node lab/E/test_trace.mjs
python3 lab/E/probe.py --report probe-next
python3 lab/E/acceptance_probe.py --report acceptance-next

# 未修改 repo 的環境驗證；既有完整 baseline 可重用。
python3 lab/E/environment.py --report e0-next --reuse-baseline

# 首次真實主線，會使用已確認的本機登入／資料傳送與訂閱額度。
lab/D/.venv/bin/python lab/E/validate.py
# 只在主線 E1 通過後執行一次。
lab/D/.venv/bin/python lab/E/followups.py
# 完成移除 worker 後離線核對。
lab/D/.venv/bin/python lab/E/audit.py
```

`continue_main.py` 是本次配置雜湊掃描競態的有界恢復入口，會核對沒有開發 turn 派發才繼續；不是通用 retry。已完成批次若要重做，需要另指定新的輸出／runtime 批次與配額，不刪除舊 ledger 來取得額外 turn。
