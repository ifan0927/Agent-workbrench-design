# 個人 Agent 工作台

為個人建立結果導向的 agent 工作台：集中維護共用約定、工作模式與 skills，依工作組裝必要配置，交由既有 Codex harness 在可拋棄環境執行，再保存成果、必要 review 與人工決定。

本公開 repo 收錄設計文件、實驗程式與結果摘要。真實專案副本、原始事件、資料庫、Git bundle、認證與執行環境僅保存在本機；公開範圍及重現限制見[實驗室說明](lab/README.md#公開範圍與本機證據)。

2026-09-11 起進入正式系統設計階段，尚無產品應用程式。[設計方法與討論順序](docs/design/README.md)已落檔，從首版使用情境開始，逐步收斂工作狀態、元件責任、契約與實作切片。各項產品與技術決策仍依主題文件的狀態判讀；進入設計不代表候選已全部定案。

A 組實驗已在 [lab/A](lab/A/README.md) 實作及執行，結果與限制見[驗證結果](lab/A/RESULTS.md)。B 組配置實驗已在 [lab/B](lab/B/README.md) 完成最小驗證，見[結果與限制](lab/B/RESULTS.md)。C 組成果與交接已在 [lab/C](lab/C/README.md) 完成最小驗證，見[結果與限制](lab/C/RESULTS.md)。D 組外層流程與環境已在 [lab/D](lab/D/README.md) 完成最小驗證，見[結果與限制](lab/D/RESULTS.md)。

[E 組：真實專案整合與執行追蹤](lab/E/README.md)已在獨立真實 repo 副本上實作及執行；各項結論與剩餘缺口見[驗證結果](lab/E/RESULTS.md)。所有變更及成果留在 lab，沒有套用到 active repo。

## 依問題閱讀

| 想了解什麼 | 文件 |
| --- | --- |
| 正式設計如何進行、先討論什麼、如何接手 | [設計方法與討論順序](docs/design/README.md) |
| 為什麼做、工作種類與不做的事 | [產品範圍](docs/product.md) |
| 技術組合、元件責任、資料與控制權 | [候選架構](docs/design/architecture.md) |
| 共用指引、專案索引與 skills 如何組裝 | [配置與按需探索](docs/design/configuration.md) |
| 訂閱、API、短效 token 與平行 worker | [認證與平行執行](docs/design/authentication.md) |
| 工作、session、成果、review 與取消 | [工作生命週期與交接](docs/design/workflow.md) |
| 優先驗證什麼、如何判斷結果 | [實驗入口](docs/experiments/README.md) |
| 如何重跑 A–E 組、哪些項目已驗證 | [實驗室](lab/README.md) |
| 真實 repo 整合如何執行與接手 | [E 組操作說明](lab/E/README.md) |
| 哪些來源讀過、哪些結論還未驗證 | [來源與證據](docs/references.md) |

接下來按設計入口討論「第一次加入專案，準備並開始一件工作」。剩餘實驗依具體設計疑問安排，不作所有設計工作的前置門檻；目前不開始產品實作或追加模型實驗。

Agent 的按需閱讀與維護約定見 [AGENTS.md](AGENTS.md)。
