# 06 跨專案共用指引

- 更新日期：2026-09-11（Asia/Taipei）
- 訪談進度：in-progress
- 本場聚焦：哪些跨專案的 agent 好習慣值得集中維護，哪些應依工作、專案或任務調整
- 摘要確認：U01–U03 為使用者明確表達；研究整理、AI 推導與完整案例摘要未另經確認

## 1. 範圍與既有基準

本題只辨認跨專案想統一改善的 agent 行為，以及必須容許工作、專案或任務差異的習慣。本場不決定配置格式、角色矩陣、skills、LangGraph nodes 或初始化實作；專案資訊維護、角色與 context 配置、外層流程政策分別交 07／08／09。

沿用 [configuration](../../docs/design/configuration.md) 的既有基準：共用工作約定應保持短小；專案資訊由索引提供用途與線索，再由 agent 按工作需要逐層探索。重要方案取捨須取得使用者選擇；已授權範圍內的純實作細節由 agent 自主處理。所有 code 相關工作須由另一個 agent review。

[05-interaction-recovery](../05-interaction-recovery/README.md) U14 提出的「平台依當次 agent 性質初始化適用設定，工作流較偏向負責流程推進」仍是候選；不預設每種工作流整份替換全局 AGENTS.md，也不預設工作流只影響 graph。

## 2. 使用者明確表達

| ID | 需求／偏好／界線 | 來源及必要原話 | 狀態與適用條件 |
| --- | --- | --- | --- |
| U01 | 本題希望搭配較新的 agent 研究與實務，先了解 best practice，再討論哪些習慣值得跨專案統一；同時承接前題「依工作給予不同指引方向與索引」的想法。 | 2026-09-11；「想搭配現有較新的 agents 研究看看 best practice 是什麼」「基於工作給予不同的指引方向索引」 | 明確回答；表示訪談需以近期資料協助產生具體比較案例，不等於使用者已採納任何外部做法或配置方案。 |

| U02 | 希望跨專案統一重視主動探索，不要憑空假設。 | 2026-09-11；選擇前輪第 2、3 類行為並說「探索的重要性 不要憑空假設」。 | 明確回答；沿用按需探索基準，不新增每次全量閱讀、固定探索步驟或證據門檻。 |
| U03 | 工作做完後，要依各工作的指引完成對應驗證。 | 2026-09-11；「做完要依照個工作的指引完成對應的驗證」。 | 明確回答；對應驗證依工作指引而定；具體驗證方式與指引缺漏時的行為尚未討論，不把選擇第 3 類延伸成所有列舉細節皆已確認。 |

## 3. 具體 journey／行為案例

| ID | 起點與必要背景 | 使用者操作／事件 | 預期系統與 agent 行為 | 可見成果／接手點 | 不得發生／待決 |
| --- | --- | --- | --- | --- | --- |
| J01 | AI 前輪提出的工作中／完成後行為，使用者明確選擇其中探索與對應驗證的方向；本列為依 U02–U03 整理，未另經整體確認。 | 使用者交代一件有適用工作指引的任務。 | 按工作需要探索實際資訊，不憑空假設；做完依該工作指引完成對應驗證。 | 完成適用驗證；具體呈現方式未問。 | 不新增全量閱讀要求；指引未寫驗證方式時如何處理仍未問。 |

## 4. 候選、未決與跨題事項

| ID | 類型 | 問題／候選 | 影響及建議去向 |
| --- | --- | --- | --- |
| O01 | AI 研究整理／待核對 | 近期一手資料共同支持分層與精簡 context：Codex 以 global guidance 加 project-specific overrides；Anthropic 建議使用最小高訊號 context、just-in-time retrieval 與 progressive disclosure；GitHub Copilot 區分 repository-wide、path-specific 與 nearest AGENTS.md 指引。 | 作為訪談例子來源，不直接升格為 Agent Workbench 需求。來源：[OpenAI AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)、[GitHub repository instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)。 |
| O02 | AI 研究整理／待核對 | Anthropic 將固定 workflow 與由模型動態決定步驟的 agent 分開，並建議從最簡單可行方案開始；routing 可讓不同工作使用較專門的指引，避免單一 prompt 為一類工作優化後傷害其他類型。 | 可用來檢查「工作指引方向／索引」是否解決真實行為問題；不據此決定 routing、角色或 graph。來源：[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)。 |
| O03 | 已回答／待整合 | U02–U03 已指出希望跨專案改善探索、不憑空假設，以及依工作指引完成對應驗證。 | 不再要求使用者選擇最重要的一類；尚未取得特定專案事件，不為補案例而重問既有答案。 |
| O04 | 跨題事項 | 工作別指引如何選取、角色 context 如何組裝屬 08；專案索引內容與維護屬 07；哪些行為由外層流程保證屬 09。 | 本題只記需要的行為與容許差異，不替其他主題選定機制。 |

| O05 | AI 推導 | 可把「探索有根據、完成適用驗證」理解為共用行為要求，將實際探索入口與驗證內容留給工作／專案指引；不要求全局同一套驗證清單。 | 由 U02–U03 與既有按需探索基準整理；不是已選定配置層級或格式。 |
| O06 | 未問 | 工作指引未說明驗證方式時，agent 應如何處理才算完成？ | 下一個具體分界問題；不要求完整分類、固定步驟或證據門檻。 |

## 5. 本場收斂與下次接續

- 本場已足以帶去統整的內容：U01 的研究校準要求，以及 U02–U03 的探索與依工作指引驗證要求已明確；本場仍 in-progress，未開始 synthesis。
- 本場未完成或刻意略過：指引缺少驗證方式時的行為尚未討論；配置與流程實作刻意不談。重要取捨、按需閱讀及另一個 agent code review 不重問。
- 下次第一個值得問的問題：例如某項工作指引沒有寫驗證方式，你希望 agent 怎麼處理，才算完成這份工作？
- 建議下一步：續本題，以研究整理後的少量具體行為例子做取捨；目前不開始 synthesis。

## 6. 整合追蹤

尚未整合。

| 已處理的來源 commit／條目 | 正式文件與段落 | 處理方式及尚待事項 |
| --- | --- | --- |
| 尚未整合 | 尚未整合 | U01–U03、J01 與 O01–O06 待後續訪談及統整；按各條目身分處理。 |
