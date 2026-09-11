# 配置組裝與按需探索

狀態：候選設計；集中維護、按需讀取與 project onboarding 邊界是使用者基準。[B 組最小實驗](../../lab/B/RESULTS.md)已驗證一種注入、發現與快照方式，尚非完整平台實作。整理日期：2026-09-11。

平台集中維護共用內容，每輪選定並固定必要版本；專案 AGENTS.md 保留少量必要約定與文件索引，不是百科或必讀清單。Agent 根據當次問題自主搜尋與探索。

## 內容分工

| 內容 | 用途 |
| --- | --- |
| 共用工作約定 | 跨專案的必要習慣與邊界，保持短小。 |
| 工作模式 | 本次研究、開發或 review 的責任與產物，不建立永久角色群。 |
| 專案索引 | 文件用途、已採納／候選／歷史身分、入口、特殊限制與建置／驗證線索。 |
| Skills | 依工作選用的可發現能力，全文由 agent 按需讀取。 |
| 任務輸入 | 當次目標、範圍、完成條件、授權、已納入的回答與成果。 |

專案索引與當次任務分開；切換模式不覆寫 repo AGENTS.md。Home `AGENTS.md` 保存跨專案習慣，repo `AGENTS.md` 主要提供專案索引與特殊規則入口；原始 repo 文件仍是 authoritative source，由 agent 按當次需要讀取。AI 可以協助起草與分類，不需要每輪自由重寫全部規則。來源資料留原處，索引不複製全文。

## 專案 onboarding 與維護

[產品基準](../product.md#專案入場與-onboarding)要求一般 Workbench 專案工作先通過 project-level onboarding。Onboarding bench agent 的責任是探索、找出真正 blockers 並提出建議，不是成為所有後續工作的永久主管：

1. 既有 repo：固定目標版本，探索文件、專案索引、特殊規則、build／test／CI 與必要 Git／tool capability。
2. 新專案：收到使用者建立 repo 的明確授權後，先建立 repo 與符合初期輪廓的骨架，再以該 repo 接續相同探索。
3. 依「看得到該看的、改得到該改的、驗得到該驗的」判斷 readiness，呈現少而精準的 blockers、實際證據與建議。
4. 使用者確認後，才把穩定的 project index、repo `AGENTS.md` 入口與 local／external verification 線索寫回 repo；寫回不取代原始文件。
5. Gate 通過前不派一般 worker。必要能力缺失時先修正並重新驗證；CI-only repo 可在 authoritative verification path 明確時通過。
6. 後續 maintenance 沿用相同探索與「建議 → 確認 → 修改」界線，但只由使用者手動觸發，不做背景監控或週期掃描。

Gate 的證據格式、能力探測、失效後重驗與初始骨架內容仍是候選設計／技術待查；issue／task 能力是否構成 blocker 留給 workflow policy 統整。Bench agent 是否長時間存在不由本節定案。

## 本輪有效配置

啟動前固定並記錄：任務與留言版本、repo commit 或研究來源、共用約定／模式／專案索引／skills 版本、worker image、Codex 版本、模型與有效設定、工具集合、工作路徑。

以精簡 manifest 保存來源、版本或雜湊、組裝順序，並保存實際組裝內容。配置快照不含秘密；共用來源更新只影響後續選用，執行中的工作不默認更新。

共用約定可透過受控 Codex home 提供；repo AGENTS.md 保留原樣，當次模式與任務另外傳入。App-server 接入下的實測欄位、衝突案例與快照方式見 [B 組結果](../../lab/B/RESULTS.md)；適用範圍限該固定版本與案例，不把 CLI 的假設直接移植。

## 衝突與發現

- 設定衝突如同名 skills、版本混用、必要工具缺失、指引截斷，組裝器應呈現或拒絕啟動。
- 語意衝突依 Codex 原生指令優先序處理；會影響目標或授權時提出必要問題。索引不能把歷史提案升格為現行規則。
- 真正可發現集合可能包含平台選用、repo、user、image 的 system／admin 來源，以及已啟用插件；不能只用 CODEX_HOME 推定已控制全部來源。
- 設定預覽、能力可發現、實際讀取、正確遵循是四件不同的事。文字索引本身不會自動替 Codex 安裝或註冊 skills。

官方說明 AGENTS.md 有分層／override 與大小上限；skills 有多個來源、同名不合併與初始清單預算。核對入口：[AGENTS.md](https://developers.openai.com/codex/guides/agents-md/)、[Skills](https://developers.openai.com/codex/skills/)。

## 如何證明生效

1. 比對 manifest 與實際檔案、掛載、路徑及設定。
2. 在同版本、同 cwd 檢查 Codex 的配置／skills 發現結果及警告；可評估 app-server 的相關查詢接口。
3. 使用小型行為案例，從產物、檔案與執行結果驗證必要限制；不以 agent 自述已讀作唯一證據。

維持共用指引排序、工具集合與工作路徑穩定，避免無意義破壞快取前綴；不承諾跨 worker 模型快取命中，也不為 cache 建立昂貴 session 遷移。成本看完整工作而非單次 cache hit。

## 本專案文件的示範方式

根目錄 [AGENTS.md](../../AGENTS.md)直接列出問題與入口，只附少量必要約定；[README](../../README.md)說明產品及目前階段。各主題自行標明狀態，一個結論一個主要位置，其他文件連結引用。這示範文件組織方式，尚不代表已實作平台配置組裝器。
