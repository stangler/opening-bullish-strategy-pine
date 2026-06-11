# tv_backtest_scraper.py — 全自動版
import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ========== 設定 ==========
URLS_FILE   = Path("urls.txt")
OUTPUT_DIR  = Path(".")
CHART_URL   = "https://jp.tradingview.com/chart/"
USER_DATA   = r"C:\Temp\tv-profile-pw"   # セッション保存先
WAIT_RECALC = 6      # バックテスト再計算待機（秒）
WAIT_SEARCH = 1.5    # 検索ダイアログ安定待機（秒）
EXCHANGE    = "TSE"
# ==========================

def load_symbols() -> list[str]:
    lines = URLS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]

def save_csv(strategy_data: list, dw_data: list, symbol: str):
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
        "純利益", "総損益", "最大ドローダウン",
        "トレード総数", "勝ちトレード", "負けトレード",
        "勝率", "プロフィットファクター", "期待値"
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
            if (key.includes("勝ちトレード") && !seen.has("勝ちトレード_first")) {
                seen.add("勝ちトレード_first");
                continue;
            }
            if (!seen.has(key)) {
                seen.add(key);
                result.push([key, val]);
            }
        }
        return result;
    }
    """, keywords)

async def scrape_data_window(page) -> list:
    # Endキーで最終バーへ移動 → Data Window更新
    await page.keyboard.press("End")
    await page.wait_for_timeout(800)

    result = await page.evaluate("""
    () => {
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
        for (let i = 0; i + 1 < texts.length; i += 2) {
            items.push([texts[i], texts[i+1]]);
        }
        return { found: true, selector: 'text-fallback', items };
    }
    """)

    if not result["found"]:
        print("  ⚠ データウィンドウ コンテナ未検出")
        return []
    print(f"  データウィンドウ: {result['selector']} / {len(result['items'])}行")
    return result["items"]

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