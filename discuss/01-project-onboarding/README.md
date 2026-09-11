# 01 Project Onboarding

- 更新日期：2026-09-11；Asia/Taipei
- 訪談進度：in-progress
- 本場聚焦：既有 repo 的 onboarding 基準，以及無 repo 起點、暫存研究／prototype 與正式 onboarding 的分界
- 摘要確認：U01–U15 為使用者在 2026-09-11 接手指令或本場問答中明確表達；J01–J07 是依這些回答整理的行為案例，案例表述仍待確認；O01–O06 保留未決、跨題或 AI 推導身分

## 1. 範圍與既有基準

本題包含：無 repo 時如何直接開始討論／研究、研究與 prototype 成果可暫存到何種程度、何時建立或指定 repo 並進入正式 onboarding；並沿用既有 repo 第一次接入時的 readiness gate、驗證路徑及低頻維護基準。

本場不談：暫存空間的 UI／資料模型／正式命名、issue／task 的完整工作模型、Workbench 對 GitHub issue 的最終能力邊界、長時間協調角色的正式架構、背景監控，以及 onboarding 後的完整開發／交付流程。

沿用下列基準；讀取版本為 commit `cbff7e02258bd900196a67c8a76351d7e41cf1e4`：

- [產品範圍與基準](../../docs/product.md#使用體驗與工作範圍)：coding 以遠端 repo 指定版本為基準；平台改善環境、目標與回饋，不預先微管理 worker 的解題路徑。這是產品基準，不代表 onboarding gate 的細節已定案。
- [配置組裝與按需探索](../../docs/design/configuration.md#內容分工)：共用約定、專案索引與任務輸入分工，原始來源留在原處，索引不複製全文；該文件整體仍標為候選設計。
- [配置衝突與發現](../../docs/design/configuration.md#衝突與發現)：必要工具缺失應呈現或拒絕啟動；能力可發現、實際讀取與正確遵循不可混為一談。
- [分題訪談入口](../README.md#固定回報與接續)與[固定模板](../_template.md)：`ready-for-synthesis` 只表示材料足以統整，不表示完整設計已批准或所有未知已消除。

## 2. 使用者明確表達

| ID | 需求／偏好／界線 | 來源及必要原話 | 狀態與適用條件 |
| --- | --- | --- | --- |
| U01 | 日常任務入口要很薄，例如只需提出「開發 GitHub issue #123」；專案長期規則不應在每次任務重述。 | 2026-09-11；本次接手指令 | 明確回答；適用於已完成 onboarding、可由專案索引按需找到長期資訊的專案 |
| U02 | 使用者願意在第一次 onboarding 投入一次性成本，也接受之後低頻維護，以換取日常任務的低輸入成本。 | 2026-09-11；本次接手指令 | 明確回答；不代表接受自動或週期性維護 |
| U03 | Onboarding 時由 bench agent 探索 repo，提出 project index／repo `AGENTS.md` 建議；使用者確認後才可修改 repo。 | 2026-09-11；本次接手指令 | 明確回答；探索與提出建議可先做，repo 寫入需另有使用者確認 |
| U04 | Home `AGENTS.md` 管跨專案習慣；repo `AGENTS.md` 主要是專案索引與特殊規則入口。原始 repo 文件仍是 authoritative source，agent 按當次需要讀取。 | 2026-09-11；本次接手指令 | 明確回答；未決定完整索引格式或所有規則的歸屬 |
| U05 | Onboarding 是 project-level global gate，不為三種 use case 各建一套 readiness matrix；gate 必須少而精準，只納入真正阻擋派工的事項。 | 2026-09-11；本次接手指令 | 明確回答；三種 use case 的其他差異不在本題定案 |
| U06 | 核心 readiness 可濃縮為「看得到該看的、改得到該改的、驗得到該驗的」。 | 2026-09-11；本次接手指令 | 明確回答；這是判斷邊界，不是已批准的資料 schema 或 UI |
| U07 | Workbench 必須確保被派出的 worker 真正具備其宣告的基礎工具能力；例如 Git 自主操作不可用時，onboarding 未完成、不得派工，應先由使用者與 bench 修正。 | 2026-09-11；本次接手指令 | 明確回答；具體探測與證明機制待設計／驗證 |
| U08 | Verification 不硬分 unit／integration taxonomy；對 onboarding 較有用的邊界是 local verification 與 external／CI verification。 | 2026-09-11；本次接手指令 | 明確回答；不否定 repo 自身使用更細測試分類 |
| U09 | 標準 worker 環境應能執行 repo 定義的合理 local verification；外部服務、secrets、正式 DB 等依賴可交給 GitHub CI。CI-only repo 也能通過 onboarding，前提是有明確的 authoritative verification path。 | 2026-09-11；本次接手指令 | 明確回答；何謂「合理」及各 repo 的權威路徑由探索與確認決定 |
| U10 | Bench agent 在 onboarding 探索 build／test／CI，協助判斷 local verification；使用者確認後，把穩定結果寫回 project index，降低後續 worker 的思考成本。 | 2026-09-11；本次接手指令 | 明確回答；寫回的是穩定索引與線索，不取代原始 build／test／CI 文件 |
| U11 | Bench agent 應具備低頻 maintenance 能力，但不做自動背景監控或週期掃描；由使用者手動觸發，重新探索 repo、提出差異與修改建議，經確認後才修改 repo。 | 2026-09-11；本次接手指令 | 明確回答；觸發方式、差異格式與維護範圍仍待設計 |
| U12 | Onboarding 與 maintenance 對 repo 的修改都遵循「先提出建議 → 使用者確認 → 再修改」。 | 2026-09-11；本次接手指令 | 明確回答；這是兩條路徑共用的寫入界線，不授權其他自動修改 |
| U13 | 完全沒有 repo 時，可直接開始需求討論與研究；不應先要求建立 project 或通過 repo onboarding。 | 2026-09-11；本場明確回答：「比較偏向直接討論與研究」 | 明確回答；適用於尚未指定 repo 的早期探索 |
| U14 | 無 repo 階段的研究成果可先落在按主題／想法分類的暫存空間，不因已有可保留產出就立即強迫建立 repo。 | 2026-09-11；本場明確回答；使用者以「有點像是 backlog」「資料夾分類主題或想法」描述方向 | 明確回答；暫存空間的正式名稱與結構未定，「backlog」只是類比 |
| U15 | 研究中為了判斷方向所做的 prototype 可繼續留在暫存空間；「做出 prototype」本身尚不足以觸發正式 onboarding。 | 2026-09-11；本場明確回答 | 明確回答；暫存 prototype 何時必須升格為 repo 仍待劃界 |

## 3. 具體 journey／行為案例

下列案例由 AI 依 U01–U15 整理，用於把明確需求轉成可接手的行為描述；使用者尚未逐案確認其完整表述。

| ID | 起點與必要背景 | 使用者操作／事件 | 預期系統與 agent 行為 | 可見成果／接手點 | 不得發生／待決 |
| --- | --- | --- | --- | --- | --- |
| J01 | 專案已通過 project-level onboarding；專案規則與權威文件已有按需入口 | 使用者提出薄任務，例如「開發 GitHub issue #123」 | Workbench 以任務和既有專案索引組裝必要背景；worker 按需讀原始文件，不要求使用者重貼長期規則 | 任務可進入後續釐清或派工；需要的專案證據可追溯到權威來源 | AI 整理、待確認；issue 是否必須是 gate 及 Workbench 能讀寫到何種程度仍未決 |
| J02 | 使用者第一次把既有 repo 接入 Workbench | 使用者啟動 onboarding，提供或選定 repo 與目標版本 | Bench agent 探索 repo 的文件、索引、特殊規則、build／test／CI 與基礎工具能力，依 U06 評估 blocker，提出 project index／repo `AGENTS.md` 與驗證路徑建議 | 使用者看到少而精準的 blockers、證據與擬議修改；確認後才寫回 repo，再重新判斷是否 ready | AI 整理、待確認；不得先修改 repo，也不得把候選索引內容當成已採納架構 |
| J03 | Onboarding 探索顯示 worker 環境宣告可做 Git 工作，但實際無法自主操作 Git | 系統準備派出 coding worker | Workbench 阻止派工，明確呈現缺失能力；使用者與 bench 修正環境後重新驗證 gate | 修正前維持 onboarding 未完成；修正並證明能力後才可接續 | AI 整理、待確認；不得因工具名稱存在或 agent 自述可用就視為通過 |
| J04 | Repo 已定義 build／test／CI，但部分驗證依賴外部服務、secrets 或正式 DB | Bench agent 判斷標準 worker 可執行的合理 local verification | 把可在 worker 環境合理執行的步驟列為 local path；把外部依賴列為 external／CI path，並指向 repo 的 authoritative verification source | 後續 worker 知道本地應跑什麼、哪些結果必須等 CI；CI-only repo 在路徑明確時可通過 onboarding | AI 整理、待確認；不得為了 gate 強迫套用 unit／integration 分類，也不得虛構本地可完成的驗證 |
| J05 | 已 onboarding 的 repo 經過一段時間後，使用者懷疑索引或驗證線索過時 | 使用者手動觸發 maintenance | Bench agent 重新探索、比對穩定資訊，提出差異、影響與建議修改；收到確認後才更新 repo | 使用者可採納、調整或拒絕建議；確認過的穩定結果供後續任務使用 | AI 整理、待確認；不得自動背景監控、週期掃描或未經確認修改 repo |
| J06 | 使用者只有一個尚未確定會實作的想法，沒有 repo | 直接提出需求、展開研究 | Workbench 允許討論與研究，把值得保留的成果放入按主題／想法分類的暫存空間 | 後續可從暫存成果接續探索，或在越過分界後交接給正式 project | AI 整理、待確認；不得以尚無 repo 為由套用 onboarding gate 或阻擋研究 |
| J07 | 無 repo 的研究需要短期 prototype 才能判斷方向 | 使用者要求製作探索性 prototype | Prototype 可在暫存空間產生並保留，不因出現程式碼就自動建立 repo 或啟動 onboarding | 研究可用 prototype 證據繼續判斷；若後續需要升格，再保留必要成果與來源交接 | AI 整理、待確認；升格觸發事件與最少交接內容仍待確認 |

## 4. 候選、未決與跨題事項

| ID | 類型 | 問題／候選 | 影響及建議去向 |
| --- | --- | --- | --- |
| O01 | 使用者未決／跨題 | Issue／task 的 source of truth 與 Workbench 對 issue 的能力邊界尚未決定；因此 GitHub／issue 是否屬於 onboarding gate 不能在本題定案。 | 影響薄任務入口、派工前資料可見性與寫回能力；帶到 `09-workflow-policy`，並視需要與 `02-clarification`、`04-development-delivery` 一起核對 |
| O02 | 跨題候選 | Bench agent 可能是長時間存在的協調角色，但這只是候選，不是本題確認的正式架構。 | 影響角色生命週期、狀態保存與責任邊界；帶到 `09-workflow-policy` 與 `docs/design/architecture.md`，不得由 onboarding 紀錄直接採納 |
| O03 | AI 推導／技術待查 | U06 可形成很小的 gate 檢查面，但「看得到／改得到／驗得到」的證據格式、探測方式、失效後重驗與 UI 尚未決定。 | 可先把三句話當產品判斷邊界；具體機制由正式設計與後續實驗決定，不在本題補成 schema |
| O04 | 跨題待整合 | Home／repo `AGENTS.md` 分工、project index 維護與按需讀取同時影響全局指引和專案上下文；本題只確認 onboarding 需要的部分。 | 統整時與 `06-global-guidance`、`07-project-context` 核對，避免在不同主題建立互相衝突的權威來源 |
| O05 | 使用者未決 | 暫存 prototype 何時不再只是探索，而必須建立／指定 repo 並通過 onboarding，尚未找到可操作的觸發事件。 | 直接影響「無 repo → 有 repo」的核心分界；本 slice 下一輪以需要延續、協作或正式工程能力的反例檢查 |
| O06 | AI 提醒／命名待決 | 「backlog」通常容易被理解為待執行任務，而非研究成果保存區；目前只保留為使用者幫助理解的類比。 | 正式名稱與資訊組織不在本場決定；避免因用詞提前綁定 UI 或資料模型 |

## 5. 本場收斂與下次接續

- 本場已足以帶去統整的內容：U01–U15 已明確回答，涵蓋既有 repo onboarding 基準，以及無 repo 可直接研究、成果與探索性 prototype 可先暫存而不觸發 gate。
- 本場未完成或刻意略過：暫存 prototype 升格為 repo 的可操作觸發事件、升格時最少交接內容、issue／task source of truth、gate 的證據與實作形式、bench agent 是否長時間存在，以及 J01–J07 的案例表述確認。
- 下次第一個值得問的問題：當暫存 prototype 開始被後續工作或其他 agent 依賴時，是否已跨過必須建立／指定 repo 並 onboarding 的界線。
- 建議下一步：續問一至兩個升格反例；界線足夠清楚後，將本題恢復為 `ready-for-synthesis`，不再新增 01 的 slice。

`ready-for-synthesis` 表示已有足夠材料供設計使用，不表示所有答案、技術或完整摘要均已確認；仍以各條目狀態為準。

## 6. 整合追蹤

尚未整合。

| 已處理的來源 commit／條目 | 正式文件與段落 | 處理方式及尚待事項 |
| --- | --- | --- |
| — | — | 尚未整合；由後續統整者以本次保存 commit 與實際處理條目補充 |
