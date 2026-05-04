import csv
from pathlib import Path
from openpyxl import load_workbook

# CSVファイルから指標を抽出
def extract_from_csv(csv_file):
    data = {}
    with open(csv_file, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        # 最初の行は銘柄
        first_row = next(reader, None)
        if first_row and len(first_row) >= 2:
            data['銘柄'] = first_row[1].strip()
        
        # 2行目はヘッダー（指標,値）なのでスキップ
        next(reader, None)
        
        # 指標と値を辞書に格納
        seen_count = {}
        for row in reader:
            if len(row) >= 2:
                key = row[0].strip()
                value = row[1].strip()
                seen_count[key] = seen_count.get(key, 0) + 1
                # 「勝ちトレード」は2番目の出現値を使用、それ以外は最初の出現のみ保持
                if key == '勝ちトレード':
                    if seen_count[key] == 2:
                        data[key] = value
                elif key not in data:
                    data[key] = value
    
    return data

# format.xlsxを更新
def update_excel(csv_data_list):
    wb = load_workbook("format.xlsx")
    ws = wb.active
    
    # ヘッダー行を取得
    headers = []
    for cell in ws[1]:
        headers.append(cell.value)
    
    print(f"Excel headers: {headers}")
    
    # 各行の銘柄を確認し、対応するCSVデータを書き込む
    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        symbol_cell = row[1]  # 銘柄は列B（インデックス1）
        if symbol_cell.value:
            symbol = str(symbol_cell.value).strip()
            print(f"\nRow {row_idx}: Looking for symbol '{symbol}'")
            
            # 対応するCSVデータを探す
            csv_data = None
            for d in csv_data_list:
                if d.get('銘柄') == symbol:
                    csv_data = d
                    break
            
            if csv_data:
                print(f"  Found CSV data: {list(csv_data.keys())}")
                # 列C: 総損益
                if '総損益' in csv_data:
                    row[2].value = csv_data['総損益']
                    print(f"  Set 総損益: {csv_data['総損益']}")
                else:
                    print(f"  Warning: '総損益' not found in CSV data")
                
                # 列D: 最大ドローダウン
                if '最大ドローダウン' in csv_data:
                    row[3].value = csv_data['最大ドローダウン']
                    print(f"  Set 最大ドローダウン: {csv_data['最大ドローダウン']}")
                else:
                    print(f"  Warning: '最大ドローダウン' not found in CSV data")
                
                # 列E: トレード総数
                if 'トレード総数' in csv_data:
                    row[4].value = csv_data['トレード総数']
                    print(f"  Set トレード総数: {csv_data['トレード総数']}")
                else:
                    print(f"  Warning: 'トレード総数' not found in CSV data")
                
                # 列F: 勝ちトレード
                if '勝ちトレード' in csv_data:
                    row[5].value = csv_data['勝ちトレード']
                    print(f"  Set 勝ちトレード: {csv_data['勝ちトレード']}")
                else:
                    print(f"  Warning: '勝ちトレード' not found in CSV data")
                
                # 列G: 負けトレード
                if '負けトレード' in csv_data:
                    row[6].value = csv_data['負けトレード']
                    print(f"  Set 負けトレード: {csv_data['負けトレード']}")
                else:
                    print(f"  Warning: '負けトレード' not found in CSV data")
                
                # 列H: 勝率
                if '勝率' in csv_data:
                    row[7].value = csv_data['勝率']
                    print(f"  Set 勝率: {csv_data['勝率']}")
                else:
                    print(f"  Warning: '勝率' not found in CSV data")
                
                # 列I: プロフィットファクター
                if 'プロフィットファクター' in csv_data:
                    row[8].value = csv_data['プロフィットファクター']
                    print(f"  Set プロフィットファクター: {csv_data['プロフィットファクター']}")
                else:
                    print(f"  Warning: 'プロフィットファクター' not found in CSV data")
            else:
                print(f"  No CSV data found for symbol '{symbol}'")
    
    # 保存（元のファイルを上書き）
    output_file = "format.xlsx"
    wb.save(output_file)
    print(f"\nSaved to {output_file}")

# メイン処理
def main():
    # CSVファイルをすべて取得
    csv_files = list(Path(".").glob("*.csv"))
    print(f"Found {len(csv_files)} CSV files")
    
    csv_data_list = []
    for csv_file in csv_files:
        data = extract_from_csv(csv_file)
        csv_data_list.append(data)
        print(f"\n{csv_file.name}: {list(data.keys())}")
    
    # Excelを更新
    update_excel(csv_data_list)

if __name__ == "__main__":
    main()