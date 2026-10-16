# tv_backtest_scraper.py — 全自動版
import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ========== 設定 ==========
FORMAT_FILE = Path("format.csv")
OUTPUT_DIR  = Path("csv")
CHART_URL   = "https://jp.tradingview.com/chart/"
USER_DATA   = r"C:\Temp\tv-profile-pw"   # セッション保存先
WAIT_RECALC = 6      # バックテスト再計算待機（秒）
WAIT_SEARCH = 1.5    # 検索ダイアログ安定待機（秒）
EXCHANGE    = "TSE"

# --- Data Window 安定化取得の設定 ---
DW_INITIAL_WAIT_MS = 1500   # Endキー押下後の初回待機（旧: 800ms固定 → 不足していた）
DW_POLL_INTERVAL_MS = 700   # ポーリング間隔
DW_MAX_ATTEMPTS = 10        # 最大ポーリング回数
DW_STABLE_CHECKS = 2        # 何回連続で同一値が取れたら「安定」とみなすか

SYMBOL_MAX_RETRIES = 2      # 整合性チェックに失敗した銘柄の再取得回数
# ==========================

def load_symbols() -> list[str]:
    with open(FORMAT_FILE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        symbols = [row["銘柄コード"].strip() for row in reader if row.get("銘柄コード", "").strip()]
    return symbols

def save_csv(strategy_data: list, dw_data: list, symbol: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", symbol)
    fn = OUTPUT_DIR / f"{safe}_{datetime.now():%Y%m%d}.csv"
    with open(fn, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["銘柄", symbol])
        w.writerow(["=== Strategy Tester ===", ""])
        w.writerow(["指標", "値"])
        w.writerows(strategy_data)
        w.writerow(["=== Data Window ===", ""])
        w.writerow(["指標", "値"])
        w.writerows(dw_data)
    print(f"  ✓ 保存 → {fn}")

async def switch_symbol(page, symbol: str):
    await page.keyboard.press("Space")
    await page.wait_for_timeout(int(WAIT_SEARCH * 1000))
    query = f"{EXCHANGE}:{symbol}"
    await page.keyboard.type(query, delay=80)
    await page.wait_for_timeout(1200)
    await page.keyboard.press("ArrowDown")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")

async def wait_for_chart_update(page, symbol: str):
    try:
        await page.wait_for_function(
            f"document.title.includes('{symbol}')",
            timeout=12000
        )
    except Exception:
        print(f"  ⚠ タイトル変化タイムアウト → sleep継続")
    await page.wait_for_timeout(int(WAIT_RECALC * 1000))

async def scrape_strategy(page) -> list:
    keywords = [
        "総損益", "最大ドローダウン",
        "プロフィットファクター"
    ]
    return await page.evaluate("""
    (keywords) => {
        const texts = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while (node = walker.nextNode()) {
            const t = node.textContent.trim();
            if (t) texts.push(t);
        }
        const result = [];
        const seen = new Set();
        // 値として有効か：数値・%・通貨記号・小数点・カンマ・符号・∅を含む
        const isNumericVal = v => /^[+\-−]?[\d,\.]+(%|円)?$/.test(v) || v === '∅' || /^[+\-−]?[\d,\.]+$/.test(v.replace(/[,]/g,''));
        for (let i = 0; i < texts.length - 1; i++) {
            const key = texts[i];
            if (!keywords.some(k => key.includes(k))) continue;
            const val = texts[i + 1];
            if (!isNumericVal(val)) continue;  // 数値でなければスキップ
            if (!seen.has(key)) {
                seen.add(key);
                result.push([key, val]);
            }
        }
        return result;
    }
    """, keywords)

DW_ANCHOR_KEYS = [
    # 前場（AM）
    "GapUp 陽", "GapUp 陰", "GapUp 勝率%",
    "GapDown 陽", "GapDown 陰", "GapDown 勝率%",
    "Cont 陽", "Cont 陰", "Cont 勝率%",
    "Sum 陽", "Sum 陰", "Sum 勝率%",
    # 後場（PM）
    "PM GapUp 陽", "PM GapUp 陰", "PM GapUp 勝率%",
    "PM GapDown 陽", "PM GapDown 陰", "PM GapDown 勝率%",
    "PM Cont 陽", "PM Cont 陰", "PM Cont 勝率%",
    "PM Sum 陽", "PM Sum 陰", "PM Sum 勝率%",
    # 前場+後場の合計
    "Total 陽", "Total 陰", "Total 勝率%",
] + [
    f"{pre}{pat} {kind}"
    for pre in ("", "PM ")
    for pat in ("GapUp", "GapDown", "Cont")
    for kind in ("損益", "総利益", "総損失")
]

async def _read_data_window_raw(page, anchor_keys=DW_ANCHOR_KEYS) -> dict:
    """
    Data Windowの現在のDOM状態を1回だけ読み取る（生の evaluate 呼び出し）。

    5016で判明したバグ対策:
    text-fallback の texts[i],texts[i+1] 機械的ペアリングは、
    チャートタイトル等の余分テキストノードが挟まると全体がオフバイワンでズレ、
    GapUp/GapDown/Cont/Sumのキーが値側に紛れ込み extract 側で拾えなくなる。
    → 位置ベースをやめ、既知ラベル文字列（anchor_keys）に完全一致するノードを
      見つけ、その直後ノードを値として取る「キーワード・アンカー方式」に変更。
      ラベル→値の隣接関係はDOM構造上必ず保たれるため、前段のズレに影響されない。
    """
    return await page.evaluate("""
    (anchorKeys) => {
        const selectors = [
            '[class*="dataWindow"]',
            '[class*="data-window"]',
            '[class*="DataWindow"]',
            '[data-name="data-window"]',
            '.chart-data-window',
        ];
        let container = null;
        for (const sel of selectors) {
            container = document.querySelector(sel);
            if (container) break;
        }
        if (!container) return { found: false, items: [] };

        const items = [];
        const titled = container.querySelectorAll('[title]');
        if (titled.length > 0) {
            titled.forEach(el => {
                const label = el.getAttribute('title') || el.textContent.trim();
                const parent = el.parentElement;
                const children = parent ? Array.from(parent.children) : [];
                const idx = children.indexOf(el);
                const valEl = children[idx + 1] || children[children.length - 1];
                const value = valEl && valEl !== el ? valEl.textContent.trim() : '';
                if (label && value) items.push([label, value]);
            });
            if (items.length > 0) return { found: true, selector: 'title-attr', items };
        }

        const texts = [];
        const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
        let node;
        while (node = walker.nextNode()) {
            const t = node.textContent.trim();
            if (t) texts.push(t);
        }

        // キーワード・アンカー方式: 既知ラベルに完全一致するノードの
        // 直後ノードを値として取得（位置ズレの影響を受けない）
        const anchorItems = [];
        const seenAnchor = new Set();
        for (let i = 0; i < texts.length - 1; i++) {
            const label = texts[i];
            if (anchorKeys.includes(label) && !seenAnchor.has(label)) {
                seenAnchor.add(label);
                anchorItems.push([label, texts[i + 1]]);
            }
        }
        if (anchorItems.length > 0) {
            return { found: true, selector: 'text-fallback-anchored', items: anchorItems };
        }

        // アンカー方式で何も拾えなかった場合のみ、旧・位置ベースにフォールバック
        for (let i = 0; i + 1 < texts.length; i += 2) {
            items.push([texts[i], texts[i+1]]);
        }
        return { found: true, selector: 'text-fallback-positional', items };
    }
    """, anchor_keys)


async def scrape_data_window(page) -> list:
    """
    Endキーで最終バーへ移動 → Data Windowを取得。

    5016銘柄で判明した不具合対策:
    固定800ms待機だと、銘柄によっては再計算・再描画が間に合わず
    GapUp/GapDown/Cont/Sumが軒並み0や∅（未反映状態）のまま
    取得してしまうことがあった。
    → 「2回連続で同じ値が取れる」まで一定間隔でポーリングし、
      値が安定してから確定させる方式に変更。
    """
    await page.keyboard.press("End")
    await page.wait_for_timeout(DW_INITIAL_WAIT_MS)

    prev_items = None
    prev_selector = None
    stable_count = 0
    final_items, final_selector = [], None

    for attempt in range(1, DW_MAX_ATTEMPTS + 1):
        result = await _read_data_window_raw(page)

        if not result["found"]:
            # コンテナ自体が見えない → もう少し待って再挑戦
            await page.wait_for_timeout(DW_POLL_INTERVAL_MS)
            continue

        items = result["items"]
        selector = result["selector"]

        if prev_items is not None and items == prev_items:
            stable_count += 1
        else:
            stable_count = 0

        prev_items, prev_selector = items, selector

        if stable_count >= DW_STABLE_CHECKS - 1:
            final_items, final_selector = items, selector
            print(f"  データウィンドウ: {selector} / {len(items)}行 "
                  f"(安定確認 attempt={attempt})")
            return final_items

        await page.wait_for_timeout(DW_POLL_INTERVAL_MS)

    # 安定しなかった場合は最後に読めた値をそのまま使う（無いよりまし）
    if prev_items is not None:
        print(f"  ⚠ データウィンドウ 値が安定しないまま最大試行回数に到達 "
              f"({prev_selector} / {len(prev_items)}行) → 最終値を使用")
        return prev_items

    print("  ⚠ データウィンドウ コンテナ未検出")
    return []


def _dw_items_to_dict(dw_data: list) -> dict:
    return {k: v for k, v in dw_data}


def _to_number(v: str) -> float:
    if v is None:
        return 0.0
    v = str(v).strip().replace(",", "").replace("∅", "0").replace("円", "").replace("%", "")
    v = v.replace("−", "-")  # 全角マイナス対応
    try:
        return float(v)
    except ValueError:
        return 0.0


def is_dw_consistent(strategy_data: list, dw_data: list) -> bool:
    """
    Strategy TesterとData Windowの整合性チェック。
    総損益が0でないのにTotal(陽+陰)=0（=トレード数0扱い）なら、
    Data Windowがまだ反映される前の状態を取得してしまった疑いが強い。
    """
    strategy = dict(strategy_data)
    dw = _dw_items_to_dict(dw_data)

    net_profit = _to_number(strategy.get("総損益", "0"))

    # 前場+後場の合計(Total)を優先。Totalが無い旧版Pineの場合は前場のSumで判定
    if "Total 陽" in dw or "Total 陰" in dw:
        total_win = _to_number(dw.get("Total 陽", "0"))
        total_lose = _to_number(dw.get("Total 陰", "0"))
    else:
        total_win = _to_number(dw.get("Sum 陽", "0"))
        total_lose = _to_number(dw.get("Sum 陰", "0"))

    if net_profit != 0 and (total_win + total_lose) == 0:
        return False
    return True

async def main():
    symbols = load_symbols()
    print(f"対象 {len(symbols)} 銘柄: {symbols}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        await page.goto(CHART_URL)

        print("=" * 50)
        print("【初回のみ】ログイン + チャート設定が必要")
        print("2回目以降はそのままEnterでOK")
        print("  1. TradingViewにログイン")
        print("  2. ストラテジー適用済みチャートを開く")
        print("  3. Strategy Testerパネルを表示")
        print("  4. データウィンドウを開く")
        print("=" * 50)
        input("準備完了 → Enter: ")

        success, failed = [], []

        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{i}/{len(symbols)}] {symbol}")
            try:
                await switch_symbol(page, symbol)
                await wait_for_chart_update(page, symbol)

                strategy_data = await scrape_strategy(page)
                dw_data       = await scrape_data_window(page)

                # 総損益はあるのにトレード数0扱い → Data Windowが未反映の疑い
                # → 銘柄を再度切り替えて取り直す
                retry_count = 0
                while not is_dw_consistent(strategy_data, dw_data) and retry_count < SYMBOL_MAX_RETRIES:
                    retry_count += 1
                    print(f"  ⚠ 整合性チェック失敗（総損益あり/トレード数0）→ 再取得 {retry_count}/{SYMBOL_MAX_RETRIES}")
                    await switch_symbol(page, symbol)
                    await wait_for_chart_update(page, symbol)
                    strategy_data = await scrape_strategy(page)
                    dw_data       = await scrape_data_window(page)

                if not is_dw_consistent(strategy_data, dw_data):
                    print("  ✗ 再取得後も整合性NG → 手動確認が必要")

                if strategy_data or dw_data:
                    save_csv(strategy_data, dw_data, symbol)
                    success.append(symbol)
                else:
                    print("  ✗ データ取得失敗")
                    failed.append(symbol)

            except Exception as e:
                print(f"  ✗ エラー: {e}")
                failed.append(symbol)

        print(f"\n{'='*50}")
        print(f"完了: 成功 {len(success)} / 失敗 {len(failed)}")
        if failed:
            print(f"失敗銘柄: {failed}")

        input("ブラウザを閉じる → Enter: ")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())