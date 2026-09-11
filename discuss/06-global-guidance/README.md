# 06 跨專案共用指引

- 更新日期：2026-09-11（Asia/Taipei）
- 訪談進度：in-progress
- 本場聚焦：哪些跨專案的 agent 好習慣值得集中維護，哪些應依工作、專案或任務調整
- 摘要確認：U01 為使用者明確表達；研究整理、分類與行為候選均尚待確認

## 1. 範圍與既有基準

本題只辨認跨專案想統一改善的 agent 行為，以及必須容許工作、專案或任務差異的習慣。本場不決定配置格式、角色矩陣、skills、LangGraph nodes 或初始化實作；專案資訊維護、角色與 context 配置、外層流程政策分別交 07／08／09。

沿用 [configuration](../../docs/design/configuration.md) 的既有基準：共用工作約定應保持短小；專案資訊由索引提供用途與線索，再由 agent 按工作需要逐層探索。重要方案取捨須取得使用者選擇；已授權範圍內的純實作細節由 agent 自主處理。所有 code 相關工作須由另一個 agent review。

[05-interaction-recovery](../05-interaction-recovery/README.md) U14 提出的「平台依當次 agent 性質初始化適用設定，工作流較偏向負責流程推進」仍是候選；不預設每種工作流整份替換全局 AGENTS.md，也不預設工作流只影響 graph。

## 2. 使用者明確表達

| ID | 需求／偏好／界線 | 來源及必要原話 | 狀態與適用條件 |
| --- | --- | --- | --- |
| U01 | 本題希望搭配較新的 agent 研究與實務，先了解 best practice，再討論哪些習慣值得跨專案統一；同時承接前題「依工作給予不同指引方向與索引」的想法。 | 2026-09-11；「想搭配現有較新的 agents 研究看看 best practice 是什麼」「基於工作給予不同的指引方向索引」 | 明確回答；表示訪談需以近期資料協助產生具體比較案例，不等於使用者已採納任何外部做法或配置方案。 |

## 3. 具體 journey／行為案例

尚未由使用者提供或認可具體行為案例。下一輪以研究對照後的實際 agent 行為例子詢問，不要求使用者先列完整規則。

## 4. 候選、未決與跨題事項

| ID | 類型 | 問題／候選 | 影響及建議去向 |
| --- | --- | --- | --- |
| O01 | AI 研究整理／待核對 | 近期一手資料共同支持分層與精簡 context：Codex 以 global guidance 加 project-specific overrides；Anthropic 建議使用最小高訊號 context、just-in-time retrieval 與 progressive disclosure；GitHub Copilot 區分 repository-wide、path-specific 與 nearest AGENTS.md 指引。 | 作為訪談例子來源，不直接升格為 Agent Workbench 需求。來源：[OpenAI AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)、[GitHub repository instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)。 |
| O02 | AI 研究整理／待核對 | Anthropic 將固定 workflow 與由模型動態決定步驟的 agent 分開，並建議從最簡單可行方案開始；routing 可讓不同工作使用較專門的指引，避免單一 prompt 為一類工作優化後傷害其他類型。 | 可用來檢查「工作指引方向／索引」是否解決真實行為問題；不據此決定 routing、角色或 graph。來源：[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)。 |
| O03 | 待訪談 | 研究只提供分層原則，尚未回答使用者最想跨專案消除的具體 agent 行為；若沒有具體失敗案例，容易把本題變成抽象規則收集。 | 下一輪用少量具體行為候選找出第一個真正值得統一的問題。 |
| O04 | 跨題事項 | 工作別指引如何選取、角色 context 如何組裝屬 08；專案索引內容與維護屬 07；哪些行為由外層流程保證屬 09。 | 本題只記需要的行為與容許差異，不替其他主題選定機制。 |

## 5. 本場收斂與下次接續

- 本場已足以帶去統整的內容：U01 可作為研究校準方式的明確需求，但尚不足以收斂共用指引內容。
- 本場未完成或刻意略過：尚未取得第一個希望跨專案統一改善的具體 agent 行為；未決定任何配置或流程方案。
- 下次第一個值得問的問題：在「先確認目標與邊界、主動按需探索、完成前自行驗證與回顧」這幾類常見行為中，哪一類最常因 agent 沒做好而需要使用者重複提醒？
- 建議下一步：續本題，以研究整理後的少量具體行為例子做取捨；目前不開始 synthesis。

## 6. 整合追蹤

尚未整合。

| 已處理的來源 commit／條目 | 正式文件與段落 | 處理方式及尚待事項 |
| --- | --- | --- |
| 尚未整合 | 尚未整合 | U01 與 O01–O04 待後續訪談及統整。 |
