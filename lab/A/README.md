# A 組實驗：認證與平行執行

契約：[A1–A6 目標](../../docs/experiments/a-authentication.md)。結果的主要維護位置：[RESULTS.md](RESULTS.md)。

採 Python 標準函式庫實作，不需安裝 Python 套件。主機須為 macOS／Linux，Python 3.11 以上；本次使用 Python 3.14.3、Codex 0.153.4 與 Docker 28.5.2。這是單主機實驗，沒有 UI、API 服務、LangGraph 或其他組別的實作。尚未執行的真實登入／刷新接手方向見[後續規劃](#後續真實認證生命週期規劃未執行)。

## 重跑方式

從專案根目錄執行：

```sh
# A3–A6：假認證、真實子程序與中斷；不連 OAuth、不呼叫模型。
python3 lab/A/test_lab.py

# 本機固定版本的介面查核；不呼叫模型。
python3 lab/A/contract.py

# 建立 A 組專用 image；只安裝在容器 image 內。
docker build --pull=false -t agent-workbench-lab-a:0.153.4 lab/A

# 真實 app-server、假 token、容器完全無網路；也比較兩種沙箱的讀檔行為。
python3 lab/A/probe.py
```

以下會使用訂閱額度。提供已獲授權、有效的 Codex ChatGPT 認證檔路徑，並為每次執行指定尚未存在的結果檔名：

```sh
python3 lab/A/live.py \
  --auth-file /absolute/path/to/auth.json \
  --model gpt-6-astra \
  --seconds 120 \
  --report live-next.json
```

`--model` 省略時使用 `model/list` 的預設模型，實際模型會記錄在證據中。每次固定兩個 worker、各一個 turn，最多各 120 秒；這是時間／任務數上限，**不是 token 或金額硬上限**。Codex 內部一次 turn 仍可能有多次模型請求；報告保存實際 token 用量，不推算未知的訂閱成本。Timeout 會嘗試 interrupt，隨後停止並移除該實驗容器，不重跑任務、不切 API。

程式拒絕覆寫既有模型結果檔。首輪證據與修正後的證據分開保存，結論只維護在 RESULTS.md，不另建逐輪文字報告。

## 實作邊界

| 檔案 | 責任 |
| --- | --- |
| [auth.py](auth.py) | 單主機刷新協調、原子保存、復原判斷、固定錯誤分類；OAuth provider 由外部注入。 |
| [rpc.py](rpc.py) | stdio 雙向 JSON-RPC、刷新回呼、請求逾時、程序清理；不輸出原始 RPC。 |
| [fake_server.py](fake_server.py)／[test_lab.py](test_lab.py) | 協定替身、兩個 worker 回呼、跨程序競爭、真正程序退出後的恢復與秘密檢查。 |
| [contract.py](contract.py) | 由固定 Codex binary 產生介面，保存九個相關 schema 的摘要與 hash。 |
| [probe.py](probe.py) | 斷網容器內以假 token 驗證外部登入介面、秘密落點與讀檔。 |
| [live.py](live.py)／[Dockerfile](Dockerfile) | 真實雙容器訂閱測試；驗證不同輸入、配置標記、session、正確答案與 turn 時間重疊。 |

刷新採每份認證一把 `flock`；等待鎖不阻塞 Python event loop。取得鎖後重讀 generation，同一舊 generation 的要求共用已保存結果。鎖只涵蓋認證更新，不鎖整段模型工作。此方法限單主機本地檔案系統，不宣稱可用於多主機／網路磁碟。

中斷狀態：`prepared` 尚未送遠端，可以接續；`in_flight` 可能已送出，不重送舊 refresh token，要求重新登入；`ready` 且 generation 已前進，直接回覆已保存的新 token。新 token 與狀態放在同一份受限檔案內原子替換並同步磁碟。測試用 `os._exit` 模擬三個程序中斷點，不能代表主機斷電的全部情境。

provider 若取得確定的拒絕回應，可回傳固定 `AuthFailure`；網路錯誤、逾時或取消而無法確認遠端結果時，保留不明狀態。已知失敗會供其他等候者沿用，無自動重試。重新登入／解除暫停尚屬人工接手，未實作完整帳號管理介面。

## 認證與成果

- 真實執行只讀指定認證檔，在主機記憶體取出 access token、帳號與方案，經 stdin 控制連線注入。refresh token、id token 不交給 worker，不複製 auth.json、不掛載日常 Codex 目錄。
- 主機的認證來源仍由既有 Codex 登入維護；這個 lab **尚未實作真實 OAuth 登入／刷新 provider**。`account/read` 明確設定 `refreshToken: false`；真實刷新回呼會回覆需要人工接手，不盲用舊 token。
- 模擬認證只留在臨時的 0700 目錄及 0600 檔案。一般 checkpoint／報告只保存 phase、generation 與驗證結果。短效 token 不寫入程序參數、環境變數或成果。
- Docker 使用非 root 使用者、唯讀根目錄與唯讀工作目錄，移除 capabilities，不掛 Docker socket。`/tmp`、`/codex-home` 是各容器的暫存記憶體掛載，容器結束即移除。
- 真實 turn 使用 `externalSandbox`，由上述 Docker 設定負責隔離，避免此主機的巢狀 Bubblewrap namespace 問題。真實容器保留模型連線所需網路；這不是網路目的地白名單或多租戶強隔離。
- 首輪使用 `read-only` Codex 沙箱；對應環境失敗證據保留。之後的程式使用修正設定，不能把舊結果誤認為新版本驗收。
- 原始 RPC、模型文字與 stderr 不落一般紀錄；stdout 只輸出檢查結果。stderr 在記憶體掃描已知 canary／token 後丟棄；不包含秘密的固定答案只保存比對結果，保留用量與任務時間。
- `results/` 是精簡證據，`.runtime/` 是可刪除測試輸入。執行結束自動清理容器與輸入；被主機強制中止時，可用 label `agent-workbench.lab=A` 找到遺留實驗容器，再逐一清理。

## 文件與適用性

[官方 app-server 文件](https://learn.chatgpt.com/docs/app-server) 描述外部 token 模式、host 刷新責任及約十秒回呼期限。本機 0.153.4 schema 的外部模式仍有內部用途註記，差異見 contract.json（本機證據：`results/contract.json`）。這次介面探測不能消除接口支援或適用條件的不確定性。

本次是使用者自己的登入、本地人工發起、合成輸入的個人實驗；沒有公開 repo、push、PR 或部署。[特定 ChatGPT CI/CD 指南](https://learn.chatgpt.com/docs/auth/ci-cd-auth) 的 repo 限制不可直接推廣為所有 Codex 使用方式，也不能從本次技術成功推論未來工作台所有情境都已確認適用。

## 後續真實認證生命週期規劃（未執行）

2026-09-10 隨 [E 組設計](../E/README.md)整理，仍是 A1／A3–A6 的剩餘驗證，不另建一套認證實驗或宣稱 provider 已選定。E 的短時間整合可先設計；E 通過不能替代本節。

| 階段 | 下一輪需完成的設計／驗證 | 證據界線 |
| --- | --- | --- |
| 登入／刷新來源 | 選定適用的登入與刷新實作、固定版本及維護來源；說明如何讓平台持有認證生命週期、重新登入與受限保存。 | 外部 token 接口本身不實作 OAuth；複製日常 auth.json 不會產生獨立刷新鏈。未選定前不寫假的真實 provider。 |
| 單 worker 真實刷新 | 在具體授權的認證來源完成一次真實刷新，核對帳號及保存狀態，再以新 access token 完成小任務。 | 分開記錄遠端刷新、保存成功、模型工作成功；主動刷新成功不等於 app-server 的刷新回呼已被觸發。 |
| 回呼與雙 worker 協調 | 設計有界觸發方式，取得 app-server 真實刷新要求；兩個要求觀察同一舊 generation 時，核對只執行一次刷新及沿用新結果。 | 如果只有人工／替身回呼，或只讓兩個 worker 使用事先更新的 token，要如實標示，不能稱真實同時回呼通過。不能無限等待自然到期或故意耗盡額度。 |
| 失敗與中斷 | 沿用既有替身／程序中斷測試，針對真實 provider 差異補最小證據。 | 撤銷、輪替日常登入、遠端已成功但未保存等操作要有對應範圍；不以破壞日常認證作預設，不重送結果不明的 refresh token。 |

本次只授權此計畫落檔；登入、真實刷新、模型執行尚未獲本輪授權。下一輪完成來源、觸發與失敗處理設計後，按當時的明確授權執行；原已授權範圍不重複索取。認證來源不明只阻擋相依的真實操作，不阻擋 E 的文件／無認證設計。

模型只記[共通 token 用量](../../docs/experiments/README.md#結果紀錄與設計決定)，不換算金額。A 的剩餘執行需另定刷新次數、模型 turn 與等待期限，不借用 E 的配額；不自動 API fallback。真實結果取得前，RESULTS.md 的「真實 OAuth 未驗證」維持原狀。
