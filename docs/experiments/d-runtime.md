# D．外層流程與環境：先用替身驗證

狀態：已獲授權完成 D1–D4 最小實作與驗證。整理日期：2026-09-10。實作見 [lab/D](../../lab/D/README.md)，實測結論、替身與未驗證邊界見 [驗證結果](../../lab/D/RESULTS.md)；D4 依使用者確認採 lab/D 合成 repo，產品架構仍未定案。

[實驗入口與執行前提](README.md) · [相關候選設計](../design/architecture.md)

| ID | 驗證問題 | 最小做法 | 通過條件 |
| --- | --- | --- | --- |
| D1 | LangGraph 是否足以承載外層流程？ | 用固定輸出的 worker 跑派發、等待、結果、人工回答與接續，加入平台重啟。 | 流程轉移集中於 LangGraph；runner 不另維護一套重試與下一步規則。若仍需完整自製 controller，重新評估採用方式。 |
| D2 | 重複派發與遲到結果如何處理？ | 在容器啟動前後模擬中斷，重送同一 attempt，再送舊 attempt 結果。 | 不重複啟動模型工作；舊結果不推進新工作。 |
| D3 | 取消能否停止正確的工作？ | 取消一個含子程序的 worker，同時保留另一 worker 執行。 | 只停止目標工作；清楚回報停止完成或狀態不明，保留已保存成果。 |
| D4 | 首個專案環境是否可用？ | 在目標主機測試固定 repo 的建置、必要 test services、網路與清理。 | 能完成指定驗證；並行工作不撞連接埠、資料目錄或測試資料。 |

LangGraph interrupt 恢復會重新執行所在節點的開頭，因此 D1／D2 要檢查實際副作用邊界，不能把 checkpoint 當成容器或程序快照。[LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
