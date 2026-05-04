# tv_backtest_scraper.py  — 簡易 + 手動更新版
import asyncio
import csv
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# 設定
CDP_PORT = 9222
OUTPUT_DIR = Path(".")
URLS_FILE = Path("urls.txt")
WAIT_LONG = 8

def load_symbols():
    return [l.strip() for l in URLS_FILE.read_text(encoding="utf-8").splitlines() 
            if l.strip() and not l.startswith("#")]

def save_csv(data, symbol):
    safe = re.sub(r'[\\/:*?"<>|]', '_', symbol)
    fn = OUTPUT_DIR / f"{safe}_{datetime.now():%Y%m%d}.csv"
    with open(fn, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows([["銘柄", symbol], ["指標", "値"]] + data)
    print(f"  保存 → {fn}")

async def main():
    symbols = load_symbols()
    print(f"対象: {symbols}")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        page = browser.contexts[0].pages[0]

        for symbol in symbols:
            print(f"\n=== {symbol} ===")
            
            # 銘柄変更
            await page.evaluate(f"""
                () => {{
                    const t = '{symbol}'.toUpperCase();
                    for (let el of document.querySelectorAll('[class*="watchlist"] *')) {{
                        if (el.textContent.includes(t)) {{ el.click(); return; }}
                    }}
                }}
            """)
            
            print("    銘柄変更後、手動で以下の操作をしてからEnterを押してください：")
            print("    1. 指標タブをクリック")
            print("    2. 必要なら戦略を一度『適用』し直す")
            print("    3. データが更新されたのを確認")
            input("    操作完了 → Enter ")
            
            # データ取得
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
            
            filtered = [r for r in raw if not any(x in r[0] for x in ["TradingView","チャート","メニュー"])]
            if filtered:
                save_csv(filtered, symbol)
            else:
                print("  データ取得失敗")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())