---
name: open-slide
description: 使用者明確要求用 open-slide、或要做「網頁版 / React 投影片（瀏覽器簡報、可簡報者檢視、可嵌互動動畫）」時使用。open-slide 是已全域安裝的 CLI（npm 套件 @open-slide/cli），用 `open-slide init <dir>` 在任一專案裡建立簡報工作區，工作區自帶 create-slide、slide-authoring、create-theme、apply-comments、current-slide 等 skills。要產 .pptx / Word / Excel 檔時不要用這個，改用 officecli / pptx skill。
---

# open-slide（全域安裝，任何專案可用）

框架：每頁是 React 元件，固定 1920×1080 畫布；用自然語言描述，由 agent 寫碼。官方：https://github.com/open-slide/open-slide（MIT）。

## 使用方式

1. 在目標專案內建立工作區（先與使用者確認資料夾名稱；中文名專案請用 `中文名_英文代號` 格式）：

   ```
   open-slide init <相對路徑資料夾>
   ```

   - 目標路徑含空白、冒號、引號會被拒絕 → 先 `cd` 到上層，改傳相對路徑。
   - 常用選項：`--no-git`、`--no-install`、`--use-pnpm`、`-n <套件名>`。
2. `cd` 進工作區 → `pnpm install` → `pnpm dev`（預覽）／`pnpm build`（輸出靜態網站到 `dist/`）。
3. **之後的作業一律在工作區內進行**：讀工作區的 `CLAUDE.md`，並用工作區 `.claude/skills/` 裡的 skills（`create-slide` 起草、`slide-authoring` 技術參考、`apply-comments` 套用瀏覽器註記）。這些 skills 由 `@open-slide/core` 管理，不要複製到使用者層級、也不要手動改；更新用 `pnpm up @open-slide/core && pnpm sync:skills`。

## 環境（2026-10 安裝時）

- Node v24.16、npm 11.13，pnpm 12.14（全域），`@open-slide/cli` 2.0.0（核心 2.2.0）。
- 升級 CLI：`npm i -g @open-slide/cli@latest`。
- pnpm 安裝時會擋部分套件的建置腳本（提示 `pnpm approve`）；實測不影響 `pnpm build`。
