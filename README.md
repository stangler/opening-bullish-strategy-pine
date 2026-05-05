# 寄付強気戦略 [Pine Script v6]

09:00（前場寄り付き）と12:30（後場寄り付き）の**始値で即エントリー**し、
最初の1本確定で即エグジットする統計検証用ストラテジー。
陽線判定を待たずエントリー → 結果的に陽線になったか・利益出たかを検証。

## 特徴

- **時間足**: 1分足・3分足・5分足
- **前場 AM** エントリー: 09:00 始値 → 09:01/03/05 終値でクローズ
- **後場 PM** エントリー: 前場最終足（11:29/11:27/11:25）始値 → 12:30〜 始値でクローズ
- **ギャップ判定**:
  - AM: 前日終値 vs 当日寄り付き始値（遅延寄り付き対応済み）
  - PM: 前場終値 vs 後場寄り付き始値（遅延寄り付き対応済み）
- **3パターン別集計**: GapUp／GapDown／Cont × 陽線・陰線本数・勝率・EV(円)、**Sum行で合計表示**
- **Statsテーブル**: Net Profit・PF・Win Rate・Max DD・DD/Profit Ratio を同一テーブルに縦ドッキング表示
- **データウィンドウ出力**: パターン別集計値（陽/陰/勝率%/EV）をデータウィンドウにも表示
- **期間指定**: デフォルト 2026/04/01〜2026/04/26

## エントリー/エグジット ロジック

### 前場 AM
1. `am_fired_today` フラグで当日 `hour >= 9` の最初の足を捕捉 → `strategy.entry("AM")`
2. 同足で `strategy.close("AM", immediately=true)`
3. 前日 `close[1]`（日足）vs 当日寄り付き `open` → ギャップ率計算
4. 買い気配等で09:00に寄り付かない場合も、実際に寄り付いた足を正しく捕捉

### 後場 PM
1. 前場最終足（11:29/11:27/11:25）で `strategy.entry("PM")`
2. `pm_fired_today` フラグで12:30〜の **最初の足**で `strategy.close("PM", immediately=true)`
3. 前場終値 vs 後場寄り付き `open` → ギャップ率計算
4. 買い気配等で12:30に寄り付かない場合も、実際に寄り付いた足を正しく捕捉

## 統計テーブル（右上表示）

- **AM/PM 各セクション**: GapUp・GapDown・Cont × 陽/陰 本数・勝率・EV(円)、**Sum行（3パターン合計）**
- **Strategy Stats セクション**: Net Profit・Gross Profit/Loss・PF・Win Rate・Total/Win/Loss Trades・Max DD(金額/%)・DD/Profit Ratio

## データウィンドウ出力

テーブルと同じパターン別集計値を `plot(..., display=display.data_window)` でデータウィンドウに出力。
最終バーにカーソルを当てると確定値を確認できる。

出力項目（AM・PM 各セクション）:

| 項目 | 内容 |
|------|------|
| `AM/PM GapUp/GapDown/Cont/Sum 陽` | 陽線本数 |
| `AM/PM GapUp/GapDown/Cont/Sum 陰` | 陰線本数 |
| `AM/PM GapUp/GapDown/Cont/Sum 勝率%` | 勝率（%） |
| `AM/PM GapUp/GapDown/Cont/Sum EV` | 1トレードあたり期待値（円） |

## 使い方

1. TradingView → 1分足/3分足/5分足 切替
2. Pineエディタ貼付 → チャートに追加
3. 入力設定で「前場 09:00 有効」「後場 12:30 有効」を選択
4. 戦略テスターで純利益・ギャップ別統計を確認

### 推奨設定

- スリッページ: 1〜2（成行のため）
- 期間: 2026年4月以降の直近データ

## スクレイパー構成

バックテスト結果を自動取得してExcelに集計するツール群。

### tv_backtest_scraper.py

TradingViewにログインし、銘柄ごとに戦略テスター＋データウィンドウの値をCSV保存。
**銘柄切替・待機・取得をすべて自動化。**

```
# 事前準備（初回のみ）

【STEP 1】PowerShell でスクリプトを実行

cd C:\Users\payor\Desktop\ContrarianGap_Strategy_PineScript\contrarian-gap-strategy-pine
uv run python tv_backtest_scraper.py


【STEP 2】初回: 開いた Chrome で TradingView にログイン
  https://jp.tradingview.com/
  ※ 2回目以降はセッションが維持されるためスキップ可


【STEP 3】ターミナルの指示に従う
  1. ストラテジー適用済みチャートを開く
  2. Strategy Testerパネルを表示
  3. データウィンドウを開く
  4. 準備完了 → Enter
  ※ 以降は銘柄切替・取得・CSV保存まで全自動
```

**自動フロー（銘柄ごと）:**
1. `urls.txt` の銘柄コードを順に読み込み
2. Space キーで検索ダイアログを開き `TSE:{コード}` を入力 → Enter で銘柄切替
3. チャートタイトル変化を検知してバックテスト再計算を待機
4. End キーで最終バーへ移動 → データウィンドウ更新
5. Strategy Tester・データウィンドウの値を取得 → CSV保存

**取得データ:**
- Strategy Tester: 総損益・勝率・PF・ドローダウン等
- Data Window: パターン別集計（陽/陰/勝率%/EV）

**データウィンドウ取得の仕組み:**
TradingViewのクラス名難読化に対応するため、5候補セレクタを順に試行。
取得できない場合はテキストノード総なめのフォールバックで対応。
TradingView更新後にクラス名が変わった場合はブラウザの検証ツールで
`data-window` 含む要素を探してセレクタを追加する。

**設定値（スクリプト冒頭）:**

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `USER_DATA` | `C:\Temp\tv-profile-pw` | セッション保存先 |
| `WAIT_RECALC` | `6` | バックテスト再計算待機（秒） |
| `WAIT_SEARCH` | `1.5` | 検索ダイアログ安定待機（秒） |
| `EXCHANGE` | `TSE` | 取引所コード |

### extract_data.py

スクレイパーが出力したCSVを読み込み、`format.xlsx` に転記。

```
python extract_data.py
```

**前提:** `format.xlsx`（テンプレート）と取得済みCSVが同一ディレクトリに存在すること。

**転記項目:**

| セクション | 項目 |
|-----------|------|
| Strategy Tester | 総損益・最大ドローダウン・トレード総数・勝ちトレード・負けトレード・勝率・プロフィットファクター |
| Data Window | AM/PM × GapUp/GapDown/Cont/Sum × 陽/陰/勝率%/EV（32項目） |

### urls.txt

スクレイパーの対象銘柄リスト（1行1銘柄コード、`#`でコメントアウト）。
取引所プレフィックス（`TSE:`）はスクリプトが自動付与するため不要。

```
# 例
7203
6758
9984
```

## 注意

- **陽線判定前エントリー** → リスクあり、検証専用
- **当日内決済** → オーバーナイト持越しなし
- AM/PMどちらか片方のみ使用可能（入力UIで個別ON/OFF）
- データウィンドウは最終バーにカーソルを当てた状態でのみ確定値が表示される

---

**Version**: 4.3（後場遅延寄り付き対応）  
**Branch**: `fix/pm-delayed-open` / `feat/data-window-export` / `feat/full-auto-scraper`  
**License**: MIT