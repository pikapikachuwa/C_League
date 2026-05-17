import sqlite3
import os
from flask import Flask, render_template, request, redirect, jsonify
from datetime import datetime

app = Flask(__name__)
DB_PATH = 'mahjong.db'

# ==================== DATABASE SETUP ====================

def init_db():
    """データベース初期化（テーブル作成）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # メンバーテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS members (
        member_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        internal_key TEXT NOT NULL,
        color TEXT NOT NULL
    )
    ''')
    
    # 試合テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_number INTEGER NOT NULL,
        play_date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 結果テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS results (
        result_id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        pts INTEGER NOT NULL,
        ai_comment TEXT,
        FOREIGN KEY (match_id) REFERENCES matches(match_id),
        FOREIGN KEY (member_id) REFERENCES members(member_id)
    )
    ''')
    
    # メンバーデータ挿入（初回のみ）
    cursor.execute('SELECT COUNT(*) FROM members')
    if cursor.fetchone()[0] == 0:
        members_data = [
            (1, '土岐', 'TK_n', '#4a90d9'),
            (2, '矢嶋', 'YaJi', '#e74c3c'),
            (3, '藤木', 'FuJi', '#e67e22'),
            (4, '松林', 'MaTsuB', '#9b59b6'),
            (5, '鹿山', 'KaYaM', '#95a5a6'),
            (6, '岡崎', 'OkaZ', '#27ae60'),
            (7, '大塚', 'OtsuK', '#c0392b'),
            (8, '河井', 'KaWa_i', '#f1c40f'),
            (9, '本井', 'MoTo_i', '#1abc9c'),
        ]
        cursor.executemany(
            'INSERT INTO members (member_id, name, internal_key, color) VALUES (?, ?, ?, ?)',
            members_data
        )
    
    conn.commit()
    conn.close()

# データベース初期化
init_db()

def get_db_connection():
    """データベース接続"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ==================== ROUTES ====================

@app.route('/')
def index():
    """メインページ - ランキング表示"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # メンバーごとの累計Pts を取得
    cursor.execute('''
    SELECT 
        m.member_id,
        m.name,
        m.internal_key,
        m.color,
        SUM(r.pts) as total_pts,
        COUNT(DISTINCT r.match_id) as match_count
    FROM members m
    LEFT JOIN results r ON m.member_id = r.member_id
    GROUP BY m.member_id
    ORDER BY total_pts DESC
    ''')
    
    rankings = cursor.fetchall()
    conn.close()
    
    return render_template('index.html', rankings=rankings)

@app.route('/record')
def record():
    """試合記録ページ"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 全メンバーを取得
    cursor.execute('SELECT * FROM members ORDER BY member_id')
    members = cursor.fetchall()
    
    # 最新の試合番号を取得
    cursor.execute('SELECT MAX(match_number) FROM matches')
    result = cursor.fetchone()
    next_match_number = (result[0] or 0) + 1
    
    conn.close()
    
    return render_template('record.html', members=members, next_match_number=next_match_number)

@app.route('/api/submit_match', methods=['POST'])
def submit_match():
    """試合データをDB に保存"""
    try:
        data = request.json
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 試合をDB に追加
        cursor.execute('''
        INSERT INTO matches (match_number, play_date)
        VALUES (?, ?)
        ''', (data['match_number'], data['play_date']))
        
        match_id = cursor.lastrowid
        
        # 各メンバーの結果を追加
        for member_data in data['results']:
            cursor.execute('''
            INSERT INTO results (match_id, member_id, pts)
            VALUES (?, ?, ?)
            ''', (match_id, member_data['member_id'], member_data['pts']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'match_id': match_id})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/ranking')
def get_ranking():
    """ランキングデータ JSON 形式で取得"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT 
        m.member_id,
        m.name,
        m.internal_key,
        m.color,
        SUM(r.pts) as total_pts,
        COUNT(DISTINCT r.match_id) as match_count
    FROM members m
    LEFT JOIN results r ON m.member_id = r.member_id
    GROUP BY m.member_id
    ORDER BY total_pts DESC
    ''')
    
    rankings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(rankings)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return "ページが見つかりません", 404

@app.errorhandler(500)
def server_error(error):
    return "サーバーエラーが発生しました", 500

# ==================== RUN ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
