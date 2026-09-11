# Agent 工作指引

本專案是個人 Agent 工作台，目前以 A–E 實驗證據進入正式系統設計。依當次問題選讀下列文件，不預讀整個 docs，也不把索引當成強制閱讀清單。

| 問題 | 按需入口 |
| --- | --- |
| 正式設計方法、討論順序、決策狀態與接手 | [docs/design/README.md](docs/design/README.md) |
| 目的、範圍、產品限制 | [docs/product.md](docs/product.md) |
| 元件、技術、資料與控制權 | [docs/design/architecture.md](docs/design/architecture.md) |
| AGENTS.md、指引、skills、配置快照 | [docs/design/configuration.md](docs/design/configuration.md) |
| 訂閱／API、登入、刷新、並行 | [docs/design/authentication.md](docs/design/authentication.md) |
| 工作、回答、成果、review、恢復與取消 | [docs/design/workflow.md](docs/design/workflow.md) |
| 實驗目標、優先度、通過條件 | [docs/experiments/README.md](docs/experiments/README.md)，再選 A–D；真實整合與追蹤見 [lab/E](lab/E/README.md) |
| 來源事實、查核日期、歷史研究 | [docs/references.md](docs/references.md) |

## 必要約定

- 以繁體中文討論與撰寫文件；程式註解使用英文。
- 依當次授權行動；候選設計與實驗目標不自行授權執行。後續明確授權成立時直接完成，不重複索取批准。
- 修改前讀相關契約與既有內容；分清使用者基準、技術建議、來源事實與待驗證假設，不把歷史專案規則搬成本專案規則。
- 一個結論保留一個主要維護位置，其餘用連結；更新既有主題，新增文件時補相關索引，不建立逐輪報告或全文副本。
- 保留無關變更，不輸出或提交憑證；未明確要求不寫入外部長期記憶。
- 文件變更檢查內容一致性、連結、分類及完整變更；通常不需應用程式測試。實驗則分開報告模擬、真實執行與未驗證項目。
