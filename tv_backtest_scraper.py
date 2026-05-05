# tv_backtest_scraper.py  — データウィンドウ取得追加版
import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

CDP_PORT = 9222
OUTPUT_DIR = Path(".")
URLS_FILE = Path("urls.txt")

def load_symbols():
    return [l.strip() for l in URLS_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]

def save_csv(strategy_data, dw_data, symbol):
    safe = re.sub(r'[\\/:*?"<>|]', '_', symbol)
    fn = OUTPUT_DIR / f"{safe}_{datetime.now():%Y%m%d}.csv"
    with open(fn, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["銘柄", symbol])
        # 戦略テスター
        w.writerow(["=== Strategy Tester ===", ""])
        w.writerow(["指標", "値"])
        w.writerows(strategy_data)
        # データウィンドウ
        w.writerow(["=== Data Window ===", ""])
        w.writerow(["指標", "値"])
        w.writerows(dw_data)
    print(f"  保存 → {fn}")

async def get_strategy_data(page):
    raw = await page.evaluate("""
    () => {
        const texts = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while (node = walker.nextNode()) {
            const t = node.textContent.trim();
            if (t) texts.push(t);
        }
        const kw = ['ファクター','損益','勝率','トレード','ドローダウン','純利益','利益','リカバリー','期待'];
        const res = [];
        for (let i = 0; i < texts.length; i++) {
            if (kw.some(k => texts[i].includes(k))) {
                res.push([texts[i], texts[i+1] || '']);
            }
        }
        return res;
    }
    """)
    return [r for r in raw if not any(x in r[0] for x in ["TradingView","チャート","メニュー"])]

async def get_data_window(page):
    """データウィンドウのplot値を取得。クラス名難読化対応で複数セレクタ試行。"""
    result = await page.evaluate("""
    () => {
        // TradingViewのデータウィンドウ候補セレクタ（難読化対応）
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

        // ラベル・値ペアを抽出
        // 構造: 各行に title(ラベル) + value のテキストノード
        const items = [];

        // 方法1: title属性持つ要素 → 兄弟or親から値取得
        const titled = container.querySelectorAll('[title]');
        if (titled.length > 0) {
            titled.forEach(el => {
                const label = el.getAttribute('title') || el.textContent.trim();
                // 値は次の兄弟要素 or 親の最後の子
                const parent = el.parentElement;
                const children = parent ? Array.from(parent.children) : [];
                const idx = children.indexOf(el);
                const valEl = children[idx + 1] || children[children.length - 1];
                const value = valEl && valEl !== el ? valEl.textContent.trim() : '';
                if (label && value) items.push([label, value]);
            });
            if (items.length > 0) return { found: true, selector: 'title-attr', items };
        }

        // 方法2: テキストノード総なめ（フォールバック）
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

    print(f"  データウィンドウ取得: {result['selector']} / {len(result['items'])}行")
    return result["items"]

async def main():
    symbols = load_symbols()
    print(f"対象: {symbols}")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        page = browser.contexts[0].pages[0]

        for symbol in symbols:
            print(f"\n=== {symbol} ===")

            print("    以下を完了してからEnterを押してください：")
            print("    1. 銘柄切替 → 戦略適用確認")
            print("    2. データウィンドウを開く（最終バーにカーソル当てる）")
            print("    3. 指標タブで数値更新を確認")
            input("    操作完了 → Enter ")

            strategy_data = await get_strategy_data(page)
            dw_data       = await get_data_window(page)

            if strategy_data or dw_data:
                save_csv(strategy_data, dw_data, symbol)
            else:
                print("  データ取得失敗")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())