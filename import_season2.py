"""
Season2_戦績データ.xlsx から SQLite DB にデータを投入するスクリプト
使い方: python import_season2.py [db_path] [xlsx_path]
"""

import sys
import sqlite3
import pandas as pd
from datetime import datetime

# ==================== 定数 ====================

# メンバーマッピング（メンバー名 → member_id）
MEMBER_MAPPING = {
    '土岐': 1,
    '藤木': 3,
    '鹿山': 5,
    '河井': 8,
    '松林': 4,
    '岡崎': 6,
    '大塚': 7,
    '矢嶋': 2,
    '本井': 9,
}

# WGランク計算用
ORDER_PTS = {1: 140, 2: 60, 3: -40, 4: -160}

# ==================== ロジック ====================

def calc_wg_rank_pt(pts, rank):
    """WGランクPt = 順位点 + スコア補正"""
    return ORDER_PTS[rank] + int(pts / 5)

def calc_rank_from_pts(match_pts):
    """
    match_pts: [(member_id, pts), ...]
    returns: [(member_id, pts, rank), ...]
    """
    sorted_results = sorted(match_pts, key=lambda x: x[1], reverse=True)
    return [(member_id, pts, i + 1) for i, (member_id, pts) in enumerate(sorted_results)]

def init_db(db_path):
    """データベースを初期化（テーブル作成）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # メンバーテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS members (
        member_id             INTEGER PRIMARY KEY,
        name                  TEXT NOT NULL,
        internal_key          TEXT NOT NULL,
        color                 TEXT NOT NULL,
        season2_final_wg_pt   INTEGER DEFAULT 0
    )
    ''')
    
    # 試合テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        match_number INTEGER NOT NULL,
        play_date    DATE NOT NULL,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 結果テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS results (
        result_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id    INTEGER NOT NULL,
        member_id   INTEGER NOT NULL,
        pts         INTEGER NOT NULL,
        rank        INTEGER,
        wg_rank_pt  INTEGER,
        ai_comment  TEXT,
        FOREIGN KEY (match_id)  REFERENCES matches(match_id),
        FOREIGN KEY (member_id) REFERENCES members(member_id)
    )
    ''')
    
    # メンバー初期データ
    cursor.execute('SELECT COUNT(*) FROM members')
    if cursor.fetchone()[0] == 0:
        members_data = [
            (1, '土岐',  'TK_n',    '#4a90d9', 2868),
            (2, '矢嶋',  'YaJi',    '#e74c3c', -942),
            (3, '藤木',  'FuJi',    '#e67e22', 45),
            (4, '松林',  'MaTsuB',  '#9b59b6', 1020),
            (5, '鹿山',  'KaYaM',   '#95a5a6', 2214),
            (6, '岡崎',  'OkaZ',    '#27ae60', 1212),
            (7, '大塚',  'OtsuK',   '#c0392b', -3312),
            (8, '河井',  'KaWa_i',  '#f1c40f', -2754),
            (9, '本井',  'MoTo_i',  '#1abc9c', -354),
        ]
        cursor.executemany(
            'INSERT INTO members (member_id, name, internal_key, color, season2_final_wg_pt) VALUES (?,?,?,?,?)',
            members_data
        )
    
    conn.commit()
    conn.close()
    print("✓ DB初期化完了\n")

def import_excel_to_db(db_path, xlsx_path):
    """Excel ファイルから DB へデータを投入"""
    
    # Excel を読み込み（行4がヘッダー）
    df = pd.read_excel(xlsx_path, sheet_name='Season2ALL', header=3)
    
    # DB 接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # match_number の管理
    current_match_number = 1
    
    # 各行を処理
    for idx, row in df.iterrows():
        # 必須カラムをチェック
        if pd.isna(row['半荘']):
            continue
        
        match_number = int(row['半荘'])
        play_date = row['活動日']
        
        # datetime を日付文字列に変換
        if isinstance(play_date, pd.Timestamp):
            play_date_str = play_date.strftime('%Y-%m-%d')
        else:
            play_date_str = str(play_date)
        
        # 参加メンバーのポイントを抽出
        match_pts = []
        for member_name, member_id in MEMBER_MAPPING.items():
            pts_val = row[member_name]
            
            # "-" または NaN はスキップ
            if pd.isna(pts_val) or pts_val == '-':
                continue
            
            try:
                pts = int(pts_val)
                match_pts.append((member_id, pts))
            except (ValueError, TypeError):
                print(f"⚠ 値解析エラー: {member_name}={pts_val}")
                continue
        
        # 参加者が4人未満の場合はスキップ
        if len(match_pts) < 4:
            print(f"⚠ スキップ: {play_date_str} 半荘{match_number} (参加者{len(match_pts)}人)")
            continue
        
        # 試合を登録
        cursor.execute(
            'INSERT INTO matches (match_number, play_date) VALUES (?, ?)',
            (current_match_number, play_date_str)
        )
        match_id = cursor.lastrowid
        
        # 順位を計算
        ranked = calc_rank_from_pts(match_pts)
        
        # 結果を登録
        for member_id, pts, rank in ranked:
            wg_pt = calc_wg_rank_pt(pts, rank)
            cursor.execute(
                'INSERT INTO results (match_id, member_id, pts, rank, wg_rank_pt) VALUES (?, ?, ?, ?, ?)',
                (match_id, member_id, pts, rank, wg_pt)
            )
        
        print(f"✓ 投入: {play_date_str} 半荘{current_match_number} (match_id={match_id}, 参加{len(ranked)}人)")
        current_match_number += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 完了: {current_match_number - 1}半荘を投入しました")

# ==================== メイン ====================

if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'mahjong.db'
    xlsx_path = sys.argv[2] if len(sys.argv) > 2 else 'Season2_戦績データ.xlsx'
    
    print(f"📊 データ投入開始")
    print(f"DB: {db_path}")
    print(f"Excel: {xlsx_path}\n")
    
    try:
        init_db(db_path)
        import_excel_to_db(db_path, xlsx_path)
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
