import csv
from pathlib import Path

STRATEGY_KEYS = [
    "総損益", "最大ドローダウン",
    "プロフィットファクター",
]

DW_KEYS_AM = [
    "GapUp 陽", "GapUp 陰", "GapUp 勝率%",
    "GapDown 陽", "GapDown 陰", "GapDown 勝率%",
    "Cont 陽", "Cont 陰", "Cont 勝率%",
    "Sum 陽", "Sum 陰", "Sum 勝率%",
]

DW_KEYS_PM = [
    "PM GapUp 陽", "PM GapUp 陰", "PM GapUp 勝率%",
    "PM GapDown 陽", "PM GapDown 陰", "PM GapDown 勝率%",
    "PM Cont 陽", "PM Cont 陰", "PM Cont 勝率%",
    "PM Sum 陽", "PM Sum 陰", "PM Sum 勝率%",
]

DW_KEYS_TOTAL = ["Total 陽", "Total 陰", "Total 勝率%"]

PATTERNS = [f"{pre}{pat}" for pre in ("", "PM ") for pat in ("GapUp", "GapDown", "Cont")]

# Pineが出力するパターン別損益（1株あたり価格差・手数料除く）
DW_KEYS_PNL = [f"{b} {k}" for b in PATTERNS for k in ("損益", "総利益", "総損失")] + ["損益検算差", "Tester取引数"]

DW_KEYS = DW_KEYS_AM + DW_KEYS_PM + DW_KEYS_TOTAL + DW_KEYS_PNL

# extractで計算する列（ロングはPine出力そのまま、ショートはロングの反転）
DERIVED_KEYS = [f"{b} {k}" for b in PATTERNS
                for k in ("ロングPF", "ショート勝率%", "ショート損益", "ショートPF")]

def _num(v):
    v = str(v).strip().replace(",", "").replace("∅", "0").replace("−", "-").replace("%", "")
    try:
        return float(v)
    except ValueError:
        return None

def add_derived(data):
    for b in PATTERNS:
        bull, bear = _num(data.get(f"{b} 陽")), _num(data.get(f"{b} 陰"))
        pnl = _num(data.get(f"{b} 損益"))
        gp, gl = _num(data.get(f"{b} 総利益")), _num(data.get(f"{b} 総損失"))
        if bull is not None and bear is not None and bull + bear > 0:
            data[f"{b} ショート勝率%"] = f"{bear / (bull + bear) * 100:.1f}"
        if pnl is not None:
            data[f"{b} ショート損益"] = f"{-pnl:.2f}"
        if gp is not None and gl is not None:
            if gl != 0:
                data[f"{b} ロングPF"] = f"{gp / abs(gl):.3f}"
            if gp != 0:
                data[f"{b} ショートPF"] = f"{abs(gl) / gp:.3f}"

def extract_from_csv(csv_file):
    data = {}
    section = None  # "strategy" | "dw"

    with open(csv_file, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue

            # 銘柄行
            if row[0].strip() == "銘柄" and len(row) >= 2:
                data["銘柄"] = row[1].strip()
                continue

            # セクション切替
            if row[0].strip() == "=== Strategy Tester ===":
                section = "strategy"
                continue
            if row[0].strip() == "=== Data Window ===":
                section = "dw"
                continue

            # ヘッダー行スキップ
            if row[0].strip() == "指標":
                continue

            if len(row) < 2:
                continue

            key   = row[0].strip()
            value = row[1].strip()

            if section == "strategy" and key in STRATEGY_KEYS and key not in data:
                data[key] = value
            elif section == "dw" and key in DW_KEYS and key not in data:
                data[key] = value

    # トレード総数・勝ちトレード・負けトレードをDW値から計算
    def _int(key):
        v = data.get(key, "")
        try:
            # float経由でint化（"18.0"等の小数文字列に対応）
            return int(float(str(v).replace(",", "").replace("∅", "0")))
        except ValueError:
            return 0

    # 前場+後場の合計（Total）を優先。旧版Pineで出力したCSV（Totalなし）は前場のSumで代用
    if "Total 陽" in data or "Total 陰" in data:
        win, lose = _int("Total 陽"), _int("Total 陰")
        data["勝率"] = data.get("Total 勝率%", "")
    else:
        win, lose = _int("Sum 陽"), _int("Sum 陰")
        data["勝率"] = data.get("Sum 勝率%", "")
    data["勝ちトレード"] = str(win)
    data["負けトレード"] = str(lose)
    data["トレード総数"] = str(win + lose)

    add_derived(data)
    return data

def update_format_csv(csv_data_list, format_path="format.csv"):
    with open(format_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    all_keys = STRATEGY_KEYS + ["トレード総数", "勝ちトレード", "負けトレード", "勝率"] + DW_KEYS + DERIVED_KEYS

    for row in rows:
        symbol = (row.get("銘柄コード") or "").strip()
        if not symbol:
            continue

        csv_data = next((d for d in csv_data_list if d.get("銘柄") == symbol), None)
        if not csv_data:
            print(f"  ✗ CSVなし: {symbol}")
            continue

        print(f"  ✓ {symbol}")
        for key in all_keys:
            if key in fieldnames and key in csv_data:
                row[key] = csv_data[key]

    with open(format_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n保存 → {format_path}")

def main():
    csv_files = list(Path("csv").glob("*.csv"))
    print(f"CSV {len(csv_files)} 件\n")

    csv_data_list = []
    for f in csv_files:
        d = extract_from_csv(f)
        csv_data_list.append(d)
        print(f"{f.name}: 銘柄={d.get('銘柄')} / {len(d)-1}項目")

    print()
    update_format_csv(csv_data_list)

if __name__ == "__main__":
    main()