# C 組驗證結果

查核日期：2026-09-10。C1–C5 的最小實驗已完成；結論限於本機合成任務與下列證據，不代表工作台架構定案。重跑方式見 [README.md](README.md)，原始目標見 [C 組契約](../../docs/experiments/c-handoffs.md)。

## 結果與證據

| 項目 | 結果 | 實際證據與界線 |
| --- | --- | --- |
| C1 程序退出與成果完整性 | 通過，模擬 | 真實子程序正常退出但缺產物、錯誤 JSON、部分輸出、尚有問題及失敗退出均不交付；保留可讀部分檔案、雜湊與缺口。11 項 [測試](test_lab.py)全部通過，摘要（本機證據：`results/tests.json`）。不驗證任意研究內容的品質。 |
| C2 worker 移除後成果重建 | 通過，真實容器＋Git | coding 工作目錄在容器 tmpfs；匯出 candidate.bundle（本機證據：`results/live-validated/candidate.bundle`）後移除容器，再從 bundle 重建。新增 `usage.md`、修改 `tags.cjs`、基準 parent 與 tree 均核對，重建後斷網容器測試成功。收取結果（本機證據：`results/live-validated/collection.json`）、測試證據（本機證據：`results/live-validated/test.json`）。已保存的提問摘要亦仍可讀。 |
| C3 fresh review 獨立性 | 通過，真實模型 | 新容器、新 Codex home、新 thread；只讀完整候選、固定需求與測試紀錄，沒有開發對話。唯讀掛載拒絕寫入。最終 review（本機證據：`results/live-validated/review.json`）無 findings，回傳相同 commit 與需求雜湊。這不是模型品質 benchmark；reviewer 未取得 bundle 實體，bundle 完整性由普通程式重建驗證。 |
| C4 新候選拒用舊證據 | 通過，真實 Git＋容器測試／本地判斷 | 對說明建立新 commit，舊測試與 review 均缺當前版本綁定；即使新版重新測試成功，舊 review 仍不能背書。負向證據（本機證據：`results/live-validated/stale-evidence.json`）。新版故意停在缺 review，未作為達標候選交付。 |
| C5 等待回答後接續 | 通過，真實模型＋合成回答事件 | 第一個 worker 提問後移除；普通留言只保存，綁定問題／需求／候選的明確回答才啟動。第二個 worker 真實 `thread/resume` 回傳 `-32600`，再以保存交接建立新 context 完成 coding。等待狀態（本機證據：`results/live-validated/waiting.json`）、留言後狀態（本機證據：`results/live-validated/after-comment.json`）、回答與交接（本機證據：`results/live-validated/implementation-input/handoff.json`）。回答由測試程式提供，未驗證真人 UI；相容且尚存在 session 的 resume 成功路徑未測。 |

執行結束、交付完整、使用者採納、下一步授權分開保存；最終候選仍為 `user_adoption: undecided`、`next_authorization: null`。C5 回答事件僅授權 fixture 的實作接續，沒有推論採納或發布權限。

獨立執行 `python3 lab/C/verify.py lab/C/results/live-validated` 的 29 項檢查全部通過，包含重新重建兩份 bundle、重播回答判斷、驗證來源與沿用證據、比對需求與輸出綁定；見 audit.json（本機證據：`results/live-validated/audit.json`）。最後再次查詢 Docker，沒有 `agent-workbench.lab=C` 容器。

## 執行中發現及修正

1. 首輪（本機證據：`results/live/report.json`）完成提問與 coding，程式驗收成功，但 Docker 後端的 `docker cp` 讀不到 tmpfs 中的 bundle。斷網容器重現後改用 `docker exec cat` 串流；另外在 commit 前保存指定部分產物。首輪沒有可重建的 coding 候選，不能算 C2 通過。
2. 修正版首個 review（本機證據：`results/live-corrected/review.json`）指出需求檔與紀錄雜湊不一致：紀錄是標準化 JSON 雜湊，檔案卻使用縮排與換行。這是未說明序列化規約的交接缺口，review 正確阻止放行。現在直接寫入標準化位元組，使 review 需求檔實際 SHA-256 等於綁定值。
3. 最終執行（本機證據：`results/live-validated/report.json`）使用 `--reuse live-corrected`，沿用完全相同的候選與已完成提問／coding 證據，只新增一個 fresh review 回合；重新重建、測試及驗證 C4。歷史失敗資料保留，沿用來源與雜湊另存，沒有把前次失敗改成成功。

這些結果支持三個實作方向：成果需完整可重建資料；review 必須拿到沒有歧義的固定需求與候選；回答接續需保存問題與明確操作。仍不需要通用證據平台或永久 reviewer agent。

## 版本、用量與未驗證項目

- Python 3.14.3；Codex 0.153.4；重用 A 組 image `sha256:6a9ceb1860a444a1e82fb2311a099f3cb855bd319c569eaa26c4b854fe846b42`。固定 `gpt-6-astra`、`low`，外部訂閱認證注入。固定介面查核見 contract.json（本機證據：`results/contract.json`），實作及共用 A 組程式雜湊見 source-manifest.json（本機證據：`results/live-validated/source-manifest.json`）。
- 每次完整執行最多三個模型 turn、每 turn 120 秒；沿用候選重審最多一個 turn。沒有 token／金額硬上限。實際共六個 turn：首輪 67,384 tokens、修正版 114,539、最終新增 review 34,291，合計 **216,214 tokens**。最終交接鏈的 100,934 包含沿用的兩回合，不能再加到總用量；快取 token 已包含於輸入。
- 認證來源檔內容未改動；成功執行的 worker 不生成 auth.json，未觀察到已知認證值進入保存輸出／stderr，沒有刷新請求、API fallback、push、PR 或部署。
- 本次兩個實作缺口由本地程式修正，沒有請真人回答 fixture；人工耗時與長期成本收益未量測。這些 token 數不能換算成未知的訂閱金額。
- 未驗證：真實 OAuth 刷新、跨主機 session 遷移、主機斷電原子性、真人回答端點、任意大型 repo／研究成果品質、獨立模型供應商 review，以及正式工作台的使用條件與可靠性。這些不是本次 C 組最小驗證的已通過聲明。
