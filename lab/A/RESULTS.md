# A 組驗證結果

查核日期：2026-09-10。通過條件以 [A1–A6](../../docs/experiments/a-authentication.md) 為準；重跑方式見 [README](README.md)。這裡是實驗結論的主要維護位置。

## 結果與證據界線

| 項目 | 結果 | 已取得的證據／尚未證明的部分 |
| --- | --- | --- |
| A1 短效 token 注入 | 修正後真實通過 | 兩個真實容器均接受外部 token，讀得預期方案、ChatGPT 帳號模式；來源帳號 claim 一致且 worker 無 auth.json。兩個小任務均 completed，JSON、worker 標記及答案全數符合預期。 |
| A2 真正平行執行 | 修正後真實通過 | 兩個不同 session 的 turn 實際重疊 **8.586 秒**；工作目錄、輸入、配置標記分離。alpha 求和得到 42，beta 排序得到 apricot,kiwi,pear，兩件工作均完成且未串答。不是只比較容器啟動時間。 |
| A3 同時刷新 | 模擬通過；真實 OAuth 未驗證 | 兩個協定替身同時回呼只刷新一次；另以兩個 host 子程序驗證檔案鎖與已保存 generation 共用。等待刷新時其他 coroutine 能前進。真實模型執行沒有觸發刷新，不作真實刷新證據。 |
| A4 刷新途中中斷 | 模擬通過 | 在送遠端前、遠端已回覆未保存、保存後未回覆，用真正子程序退出測試。分別接續、要求重新登入、沿用新 generation。取消及八秒回呼期限後也不重送狀態不明的 token。OAuth 遠端是替身，未測真實輪替或主機斷電。 |
| A5 撤銷／逾時／額度 | 固定錯誤模擬通過 | 撤銷要求重新登入，速率限制／逾時暫停，額度不足另列；已知失敗供其他請求沿用，無外層自動重試或 API fallback。未撤銷日常認證、未故意耗盡訂閱。 |
| A6 日常認證與秘密 | 本次檢查通過 | 真實測試前後日常 auth.json 位元組指紋相同；worker 沒有 refresh token 或 auth.json。斷網真實 app-server 假 token 探測檢查程序參數、環境、可寫檔案與 stderr；模擬檢查 0700／0600 儲存及一般 checkpoint 無秘密。不是任意攻擊情境的完整安全驗收。 |

## 真實環境與修正

主機為 macOS；Python 3.14.3、Docker Engine 28.5.2，主機與容器 Codex 均為 **0.153.4**。容器以 `node:22.22.0-bookworm` 建立，只安裝固定版本 `@openai/codex`；實際 image ID 見模型證據。

首輪原生 Codex `read-only` 沙箱與本機 Docker 環境不相容。無模型的 `command/exec` 重現讀檔失敗，錯誤為 Bubblewrap 無權限建立 namespace。改為 `externalSandbox`、由原有非 root／唯讀 Docker 容器負責隔離後，同一讀檔檢查通過；沒有提升容器權限或修改主機 kernel 設定。

首輪兩個任務都回報 completed，但答案驗證失敗。首輪未保存原始模型文字，因此不能確定模型實際回答內容；讀檔問題由獨立無模型探測證實。程式已補 JSON／worker／result 各自比對資訊，保留一般證據的無秘密邊界。使用者明確允許追加兩個任務後，修正設定的真實驗證全數通過；首輪失敗證據仍保留。

## 用量與人工接手

首輪由使用者確認沿用目前登入，兩個任務各最多 120 秒，使用當時 `model/list` 預設的 **gpt-6-astra**。沒有 API key fallback，也沒有 OAuth 刷新。

| 執行／worker | Input tokens | Cached input tokens（包含在 input 內） | Output tokens | Total tokens |
| --- | --- | --- | --- | --- |
| 首輪 alpha | 46,092 | 24,192 | 130 | 46,222 |
| 首輪 beta | 46,092 | 24,192 | 131 | 46,223 |
| 修正後 alpha | 24,507 | 12,032 | 48 | 24,555 |
| 修正後 beta | 24,515 | 12,032 | 55 | 24,570 |
| 全部合計 | 141,206 | 72,448 | 364 | 141,570 |

修正後兩個任務合計 49,125 tokens，使用相同模型與各 120 秒上限；真實模型總計四個 turn，分兩次明確授權執行。一個 turn 含讀檔工具及 Codex 自帶指引，不能把小任務當成只有幾十個輸入 tokens。未量測訂閱的金額成本、人工節省或長期維護收益。人工接手為認證來源及追加用量各一次確認；此次不用重新登入。

## 精簡機器證據

- simulation.json（本機證據：`results/simulation.json`）：14 項假 OAuth／真實子程序測試，含測試名稱、通過數及執行時間。
- contract.json（本機證據：`results/contract.json`）：九項本機產生的接口摘要與 schema hash，涵蓋初始化、外部登入、刷新、turn、取消及 skills 發現。
- probe.json（本機證據：`results/probe.json`）：斷網容器、假 token、秘密落點檢查，以及修正前後的讀檔差異。
- live.json（本機證據：`results/live.json`）：首輪真實雙容器、帳號模式、用量、時間重疊及失敗比對；保留原結果，不改成修正後證據。
- live-corrected.json（本機證據：`results/live-corrected.json`）：修正後雙容器真實通過的證據、各自 session、答案比對、用量與重疊時間。
- source-manifest.json（本機證據：`results/source-manifest.json`）：本次整理後的實驗程式與容器定義指紋；首輪模型執行早於沙箱修正，不能套用此指紋宣稱首輪已測最新程式。

## 對設計的影響與剩餘未知

短效 token 注入與雙容器獨立工作在本次固定版本、帳號與環境下成立；可繼續評估此接入候選，沒有證據要求把整個平台序列化。刷新協調的單主機機制在模擬下成立，但尚未回答真實 OAuth provider 的選擇、輪替語義與維護負擔。當前 lab 只讀既有 Codex 登入，尚未實作平台自有登入／刷新服務。

[官方 app-server 文件](https://learn.chatgpt.com/docs/app-server) 把外部 token 登入列為實驗性、由 host 管理生命週期；本機 schema 還保有內部用途註記。技術可接入與接口正式支援、個人工作台未來用途的適用性是不同結論；本次不宣稱後兩者已確認。

未執行：真實 OAuth 刷新、真實撤銷／額度耗盡、長期並行可靠性、獨立平台登入、跨主機協調與多租戶隔離。真實刷新可能輪替日常認證，本輪沒有取得該操作授權，也沒有執行。B／C／D、產品 UI、push／PR／部署均不在此次實作範圍。
