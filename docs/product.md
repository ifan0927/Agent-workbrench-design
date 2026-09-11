# 產品範圍與基準

狀態：使用者交接與後續討論確立的產品意圖；技術尚未定案。整理日期：2026-09-11。

工作台為個人集中維護共用約定、模式、專案探索入口與選用 skills，協助釐清當次目標，並交給既有 Codex harness 在授權範圍內自主工作，減少跨專案反覆準備與人工搬運背景、成果的負擔。

## 產品假設

對選定工作，優先相信現代模型能自行探索、規劃、實作與修正。平台改善環境、目標與回饋，不預先微管理解題路徑。這是待以實際工作檢查的假設，不是成果永遠正確的保證。

四項基準：集中維護但不全部載入；允許探索但不無限擴張；保留摘要但不丟掉證據；可以恢復但不盲目重做。新增流程或角色要說明解決的具體問題與成本。

## 使用體驗與工作範圍

| 面向 | 使用者基準 |
| --- | --- |
| 工作入口 | 討論／需求釐清、設計／技術研究、開發／修正；不必依序全走。 |
| 互動 | Issue／留言區式：下目標、補資訊、回答必要問題、採納成果、要求接續或取消；重視成果，不要求即時顯示完整執行過程。 |
| 配置 | 平台集中維護共用內容，專案提供差異、必要限制與探索入口；能力可發現不等於強制使用。 |
| Repo | Workbench 專案以遠端 repo 指定版本為基準，不管理或同步使用者本機 checkout；不建立可長期工作的無 repo project。 |
| 環境 | 工作環境可拋棄；保存工作身分、配置與成果，不承諾原程序與未保存工作永續存在。 |
| 安全取向 | 個人可信專案、容器化與基本憑證管理；不以任意惡意程式或多租戶強隔離為目標。 |
| 工程策略 | 傾向自建產品層，底層優先採用能減少長期責任的能力；不為套用現成平台扭曲工作模型。 |
| Repo 拆分 | 偏好少數粗粒度元件，避免單一大型 repo；不因此拆微服務或預建全部 repos。 |

## 專案入場與 onboarding

最早期、可能很快放棄的模糊想法與無 repo prototype 可先在原生 ChatGPT 或其他外部探索空間進行，不受 Workbench onboarding gate 阻擋。當想法已有初期專案輪廓且使用者決定交給 Workbench，便啟動 project onboarding：已有 repo 就指定版本後探索；尚無 repo 則可明確授權 bench agent 在 onboarding 內建立 repo 與初始骨架，再接續同一套 gate。Repo 建立成功不等於 onboarding 已完成，也不因此允許先派一般 worker。

Onboarding 是跨工作類型共用的 project-level global gate，不為討論、研究與開發各建一套 readiness matrix。Gate 只保留真正阻擋派工的事項，核心判斷是「看得到該看的、改得到該改的、驗得到該驗的」：

- Bench agent 探索 repo 的文件、專案索引、特殊規則、build／test／CI 與必要工具能力，提出 blockers、證據及 project index／repo `AGENTS.md`／驗證路徑建議。
- 必要 Git／tool capability 必須實際可用，不能只因工具可發現或 agent 自述可用就視為通過；缺失時先由使用者與 bench 修正，不派 worker。
- 標準 worker 應能執行 repo 定義的合理 local verification；外部服務、secrets、正式資料庫等可由 authoritative CI／external path 驗證。CI-only repo 在權威路徑明確時仍可通過 onboarding。
- Onboarding 與後續 maintenance 對 repo 的修改都先提出建議，經使用者確認後才執行。Maintenance 只由使用者手動觸發，不做自動背景監控或週期掃描。

初期輪廓、骨架與交接成果的具體格式，gate 證據 schema／探測方式，以及 issue 是否屬於 blocker 尚未定案；它們不改變上述產品邊界。

成功不只看完成時間。人工準備、接手、review 與維護成本，和全部模型工作成本分開觀察；目前沒有兩者交換比例、金額上限或已量測的節省幅度。

## 單次目標釐清與階段銜接

已確認基準，來源：[02-clarification](../discuss/02-clarification/README.md) U01–U11。Project 已通過 onboarding 後，可以從模糊的單次目標開始；任務細節不足不代表需要重新 onboarding 或 maintenance。

需求探索收斂後可接續設計討論，不必另設一次開始確認；從設計進入開發前須取得使用者確認。這不把三種工作入口改成必走的線性關卡，也不因方案已選定就自動授權開發。目標、方案取捨與純實作細節的自主界線，主要維護於 [workflow](design/workflow.md#目標釐清與必要取捨)；索引與按需閱讀規則見 [configuration](design/configuration.md#索引與閱讀自主性)。

Clarification 多輪等待時的 session 連續性與手動中斷需求見 [workflow](design/workflow.md#clarification-的連續性)。工作環境可拋棄的原則不能直接推成每輪問答都可回收原 session；保存與恢復的技術機制仍待評估。

## 研究與設計的成果方向

已確認基準，來源：[03-research-design](../discuss/03-research-design/README.md) U01–U04。目標已清楚時，使用者主要需要貼合該 repo 的解決方案與架構。Repo 本身性質、是否過度設計、解方成本及對現代 AI agent 的合適性，是研究的起始考量，並非封閉清單；agent 仍應依任務辨認其他相關面向。

是否需要研究、何時足夠、可保留的實作待驗證事項與成果接手需求，主要維護於 [workflow](design/workflow.md#研究交付或等待回答)。成本種類與 AI agent 合適性的具體面向尚未細分，不先將它們定成固定架構、工具選型或完整評估表。

## 開發的任務交接與完成界線

已確認基準，來源：[04-development-delivery](../discuss/04-development-delivery/README.md) U01–U02／J01。需求／設計銜接開發時，以固定格式 issue 任務單承接；開發成果以該 issue 在程式上的完成為準。階段位置、授權及 PR 通過／合併的區分，主要維護於 [workflow：Issue 任務單與程式完成](design/workflow.md#issue-任務單與程式完成)。具體格式與交付呈現仍待設計，不把既有候選流程視為已採納。

## 明確不納入

- 不重啟已封存 ALC，也不承接 ALC、CodeRail 或 Multica-local 的完整 roadmap。
- 不做本機 repo 同步、完整自治交付、任意程序救援或所有環境問題自動排除。
- 不重建 Codex 內部 agent loop、不接管每輪 prompt、不預設 LLM 主管或大量永久專職角色。
- 不做完整即時聊天／IDE、與原生 Codex 雙主控、workflow 拖拉編輯器、plugin marketplace、多節點排程或多租戶平台。
- 合併、部署與維運不自動納入工作交付；K8s、獨立 publisher、憑證代理不是既定要求。

## 已修正與保留未知

- 「同一份認證刷新需要協調」不能推成「平台只能有一個 run」。平行執行是需要驗證的能力，沒有採納全平台單 worker 限制。
- 保留訂閱是重要偏好，不保證所有自動化情境均適用；API fallback 需可見且獲授權。
- 開發→驗證→review→有限修正為候選骨架，不要求每類工作都 review。一般測試可由程式執行。
- 先驗證會改變架構的接縫，再收斂完整設計；不要求調查所有工具或驗完所有例外才開始設計。
- 舊研究仍涵蓋部署／維運、尚未傾向自建的部分，以本次收斂範圍為準。市場工具能力不能依舊摘要否定；只引用實際查核內容。

技術建議見[候選架構](design/architecture.md)，驗證優先度見[實驗入口](experiments/README.md)，歷史與官方查核邊界見[來源](references.md)。
