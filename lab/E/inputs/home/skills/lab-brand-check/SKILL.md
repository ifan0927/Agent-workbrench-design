---
name: lab-brand-check
description: 在 E 組 範例品牌網站 副本驗證消息日期變更，使用 repo 本地 API fixture 執行測試與完整 build。
---

這個實驗的套件已按 lockfile 準備在 /work/node_modules；不必安裝。

- 探索回合可執行 `node /codex-home/skills/lab-brand-check/scripts/check.mjs inspect` 核對工作目錄、Node、fixture 與 news 原始檔。此命令不修改 repo。
- 開發完成後執行 `node /codex-home/skills/lab-brand-check/scripts/check.mjs test` 跑原 repo 測試。
- `build` 模式在同容器啟動本地 fixture，注入 SITE_URL 與 BRAND_API_BASE_URL，再跑完整 `npm run build`。測試模式不注入 build 專用環境，否則「缺少變數」案例會被干擾。

Controller 另外核對不可改的日期矩陣及非法文章 build；新增測試不能取代它。只讀 review 可讀取既有驗證紀錄，不必在唯讀 checkout 重跑會寫入 cache 的命令。
