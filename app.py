import sqlite3
import os
import math
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)
DB_PATH = 'mahjong.db'

# ==================== 定数 ====================

# 順位点（1着〜4着）
ORDER_PTS = {1: 140, 2: 60, 3: -40, 4: -160}

# WGランク閾値（HTMLのTHRESHOLDSと完全一致）
RANK_THRESHOLDS = [
    {'min': 4000,  'max': None,  'rank': '魂天', 'grade': '',   'cls': 'konten',  'bar': '#ffd700'},
    {'min': 2667,  'max': 4000,  'rank': '雀聖', 'grade': 'Ⅲ', 'cls': 'jusei',   'bar': '#ce93d8'},
    {'min': 1833,  'max': 2667,  'rank': '雀聖', 'grade': 'Ⅱ', 'cls': 'jusei',   'bar': '#ba68c8'},
    {'min': 1500,  'max': 1833,  'rank': '雀聖', 'grade': 'Ⅰ', 'cls': 'jusei',   'bar': '#9c27b0'},
    {'min': 1000,  'max': 1500,  'rank': '雀豪', 'grade': 'Ⅲ', 'cls': 'jugo',    'bar': '#90caf9'},
    {'min': 500,   'max': 1000,  'rank': '雀豪', 'grade': 'Ⅱ', 'cls': 'jugo',    'bar': '#42a5f5'},
    {'min': 0,     'max': 500,   'rank': '雀豪', 'grade': 'Ⅰ', 'cls': 'jugo',    'bar': '#1565c0'},
    {'min': -500,  'max': 0,     'rank': '雀傑', 'grade': 'Ⅲ', 'cls': 'juketsu', 'bar': '#a5d6a7'},
    {'min': -1000, 'max': -500,  'rank': '雀傑', 'grade': 'Ⅱ', 'cls': 'juketsu', 'bar': '#66bb6a'},
    {'min': -1500, 'max': -1000, 'rank': '雀傑', 'grade': 'Ⅰ', 'cls': 'juketsu', 'bar': '#2e7d32'},
    {'min': -2167, 'max': -1500, 'rank': '雀士', 'grade': 'Ⅲ', 'cls': 'jushi',   'bar': '#b0bec5'},
    {'min': -2833, 'max': -2167, 'rank': '雀士', 'grade': 'Ⅱ', 'cls': 'jushi',   'bar': '#90a4ae'},
    {'min': -3500, 'max': -2833, 'rank': '雀士', 'grade': 'Ⅰ', 'cls': 'jushi',   'bar': '#546e7a'},
    {'min': -4000, 'max': -3500, 'rank': '初心', 'grade': 'Ⅲ', 'cls': 'shoshin', 'bar': '#bcaaa4'},
    {'min': -4500, 'max': -4000, 'rank': '初心', 'grade': 'Ⅱ', 'cls': 'shoshin', 'bar': '#a1887f'},
    {'min': None,  'max': -4500, 'rank': '初心', 'grade': 'Ⅰ', 'cls': 'shoshin', 'bar': '#795548'},
]

# Season2最終WGランクPt（引継ぎPt × 3 で逆算）
# 引継ぎPt = Season2最終WGランクPt ÷ 3 → Season2最終 = inheritPt × 3
SEASON2_FINAL_WG_PT = {
    1: 2868,   # 土岐  : 956 × 3
    2: -942,   # 矢嶋  : -314 × 3
    3: 45,     # 藤木  : 15 × 3
    4: 1020,   # 松林  : 340 × 3
    5: 2214,   # 鹿山  : 738 × 3
    6: 1212,   # 岡崎  : 404 × 3
    7: -3312,  # 大塚  : -1104 × 3
    8: -2754,  # 河井  : -918 × 3
    9: -354,   # 本井  : -118 × 3
}

# ==================== WGランク計算ロジック ====================

def get_rank_info(wg_pt):
    """WGランクPtからランク情報を返す（HTMLのgetRankInfo関数と同じ）"""
    for t in RANK_THRESHOLDS:
        above_min = t['min'] is None or wg_pt >= t['min']
        below_max = t['max'] is None or wg_pt < t['max']
        if above_min and below_max:
            return t
    return RANK_THRESHOLDS[-1]

def get_next_rank(current_threshold):
    """1つ上のランク閾値を返す（HTMLのgetNextRank関数と同じ）"""
    idx = RANK_THRESHOLDS.index(current_threshold)
    return RANK_THRESHOLDS[idx - 1] if idx > 0 else None

def get_prev_rank(current_threshold):
    """1つ下のランク閾値を返す（HTMLのgetPrevRank関数と同じ）"""
    idx = RANK_THRESHOLDS.index(current_threshold)
    return RANK_THRESHOLDS[idx + 1] if idx < len(RANK_THRESHOLDS) - 1 else None

def calc_bar_pct(threshold, wg_pt):
    """ランク帯内のプログレスバー進捗率を返す（0〜100）"""
    if threshold['max'] is None:
        return 100.0
    if threshold['min'] is None:
        return 0.0
    pct = (wg_pt - threshold['min']) / (threshold['max'] - threshold['min']) * 100
    return round(min(100.0, max(0.0, pct)), 1)

def calc_wg_rank_pt(pts, rank):
    """
    WGランクPt = 順位点 + スコア補正
    順位点: 1着+140 / 2着+60 / 3着-40 / 4着-160
    スコア補正: pts ÷ 5（端数切り捨て）
    """
    order_pt = ORDER_PTS.get(rank, 0)
    score_bonus = int(pts / 5)
    return order_pt + score_bonus

def calc_next_target(total_wg_pt, wg_rank_pt_per_game):
    """
    次のランクまでの情報を計算する
    HTMLのnextTargetHtml関数のロジックをPythonで実装
    """
    t = get_rank_info(total_wg_pt)
    next_t = get_next_rank(t)
    prev_t = get_prev_rank(t)

    if next_t is None:
        return {'status': 'max', 'message': '魂天達成'}

    need_pt = next_t['min'] - total_wg_pt

    if wg_rank_pt_per_game > 0:
        games_needed = math.ceil(need_pt / wg_rank_pt_per_game)
        return {
            'status': 'ascending',
            'next_rank': next_t['rank'] + next_t['grade'],
            'need_pt': need_pt,
            'games_needed': games_needed,
            'ptg': wg_rank_pt_per_game,
        }
    elif wg_rank_pt_per_game < 0 and prev_t:
        drop_pt = total_wg_pt - prev_t['max']
        drop_games = math.ceil(drop_pt / abs(wg_rank_pt_per_game))
        return {
            'status': 'descending',
            'prev_rank': prev_t['rank'] + prev_t['grade'],
            'drop_pt': drop_pt,
            'drop_games': drop_games,
            'ptg': wg_rank_pt_per_game,
        }
    else:
        return {
            'status': 'flat',
            'next_rank': next_t['rank'] + next_t['grade'],
            'need_pt': need_pt,
        }

# ==================== 1試合の順位計算 ====================

def calc_rank_from_pts(match_results):
    """
    1試合の4人分のptsから順位を計算する
    引数: [(member_id, pts), ...]
    返値: [(member_id, pts, rank), ...]
    ptsが高い順に1位〜4位を付与
    """
    sorted_results = sorted(match_results, key=lambda x: x[1], reverse=True)
    return [(member_id, pts, i + 1) for i, (member_id, pts) in enumerate(sorted_results)]

# ==================== 統計計算ロジック ====================

def calculate_stats(results):
    """
    メンバーの全統計を計算する
    引数: [{'pts': int, 'rank': int, 'wg_rank_pt': int}, ...]
    HTMLダッシュボードのDATA配列に入っているすべての指標を計算
    """
    if not results:
        return None

    games = len(results)
    ranks      = [r['rank']       for r in results]
    pts_list   = [r['pts']        for r in results]
    wg_pts     = [r['wg_rank_pt'] for r in results if r['wg_rank_pt'] is not None]

    r1 = ranks.count(1)
    r2 = ranks.count(2)
    r3 = ranks.count(3)
    r4 = ranks.count(4)

    total_pts    = sum(pts_list)
    mean_pts     = total_pts / games
    variance     = sum((x - mean_pts) ** 2 for x in pts_list) / games
    std_dev      = math.sqrt(variance)

    pts_1st = [r['pts'] for r in results if r['rank'] == 1]
    pts_4th = [r['pts'] for r in results if r['rank'] == 4]

    s3_wg_rank_pt       = sum(wg_pts)
    wg_rank_pt_per_game = round(s3_wg_rank_pt / games, 1) if games > 0 else 0.0

    # 直近20戦の平均順位
    recent_results = results[-20:] if len(results) >= 20 else results
    recent_ranks   = [r['rank'] for r in recent_results]
    recent_avg_rank = round(sum(recent_ranks) / len(recent_ranks), 2) if recent_ranks else None

    return {
        'games':               games,
        'avg_rank':            round(sum(ranks) / games, 2),
        'top_rate':            round(r1 / games * 100, 1),          # Top率（1着率）
        'ren_rate':            round((r1 + r2) / games * 100, 1),   # 連帯率（1+2着率）
        'avoid_rate':          round((games - r4) / games * 100, 1),# 4着回避率
        'last_rate':           round(r4 / games * 100, 1),          # ラス率（4着率）
        'plus_rate':           round(sum(1 for p in pts_list if p > 0) / games * 100, 1),
        'std_dev':             round(std_dev, 1),
        'avg_pts_1st':         round(sum(pts_1st) / len(pts_1st), 1) if pts_1st else None,
        'avg_pts_4th':         round(sum(pts_4th) / len(pts_4th), 1) if pts_4th else None,
        'total_pts':           total_pts,
        'pts_per_game':        round(total_pts / games, 1),
        'max_pts':             max(pts_list),
        'min_pts':             min(pts_list),
        'r1': r1, 'r2': r2, 'r3': r3, 'r4': r4,
        's3_wg_rank_pt':       s3_wg_rank_pt,
        'wg_rank_pt_per_game': wg_rank_pt_per_game,
        'recent_avg_rank':     recent_avg_rank,
    }

# ==================== データベース初期化 ====================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # メンバーテーブル（season2_final_wg_pt を追加）
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

    # 結果テーブル（rank と wg_rank_pt を追加）
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

    # 既存DBへのカラム追加（マイグレーション）
    for sql in [
        'ALTER TABLE members ADD COLUMN season2_final_wg_pt INTEGER DEFAULT 0',
        'ALTER TABLE results ADD COLUMN rank INTEGER',
        'ALTER TABLE results ADD COLUMN wg_rank_pt INTEGER',
    ]:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass  # カラムが既に存在する場合はスキップ

    # メンバーデータ挿入（初回のみ）
    cursor.execute('SELECT COUNT(*) FROM members')
    if cursor.fetchone()[0] == 0:
        members_data = [
            (1, '土岐',  'TK_n',    '#4a90d9', SEASON2_FINAL_WG_PT[1]),
            (2, '矢嶋',  'YaJi',    '#e74c3c', SEASON2_FINAL_WG_PT[2]),
            (3, '藤木',  'FuJi',    '#e67e22', SEASON2_FINAL_WG_PT[3]),
            (4, '松林',  'MaTsuB',  '#9b59b6', SEASON2_FINAL_WG_PT[4]),
            (5, '鹿山',  'KaYaM',   '#95a5a6', SEASON2_FINAL_WG_PT[5]),
            (6, '岡崎',  'OkaZ',    '#27ae60', SEASON2_FINAL_WG_PT[6]),
            (7, '大塚',  'OtsuK',   '#c0392b', SEASON2_FINAL_WG_PT[7]),
            (8, '河井',  'KaWa_i',  '#f1c40f', SEASON2_FINAL_WG_PT[8]),
            (9, '本井',  'MoTo_i',  '#1abc9c', SEASON2_FINAL_WG_PT[9]),
        ]
        cursor.executemany(
            'INSERT INTO members (member_id, name, internal_key, color, season2_final_wg_pt) VALUES (?,?,?,?,?)',
            members_data
        )
    else:
        # 既存メンバーのseason2_final_wg_ptを更新
        for member_id, final_pt in SEASON2_FINAL_WG_PT.items():
            cursor.execute(
                'UPDATE members SET season2_final_wg_pt = ? WHERE member_id = ?',
                (final_pt, member_id)
            )

    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ==================== ルーティング ====================

@app.route('/')
def index():
    """メインページ（ランキング表示）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT m.member_id, m.name, m.internal_key, m.color,
           COALESCE(SUM(r.pts), 0) as total_pts,
           COUNT(r.result_id) as match_count
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
    cursor.execute('SELECT * FROM members ORDER BY member_id')
    members = cursor.fetchall()
    cursor.execute('SELECT MAX(match_number) FROM matches')
    result = cursor.fetchone()
    next_match_number = (result[0] or 0) + 1
    conn.close()
    return render_template('record.html', members=members, next_match_number=next_match_number)


@app.route('/api/submit_match', methods=['POST'])
def submit_match():
    """
    試合データをDBに保存
    ・4人分のptsから順位を自動計算
    ・WGランクPtを自動計算して保存
    """
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()

        # 試合を登録
        cursor.execute(
            'INSERT INTO matches (match_number, play_date) VALUES (?, ?)',
            (data['match_number'], data['play_date'])
        )
        match_id = cursor.lastrowid

        # 4人分のptsから順位を計算
        match_pts = [(r['member_id'], r['pts']) for r in data['results']]
        ranked = calc_rank_from_pts(match_pts)

        # 各メンバーの結果を保存（rank・wg_rank_pt も自動計算）
        for member_id, pts, rank in ranked:
            wg_pt = calc_wg_rank_pt(pts, rank)
            cursor.execute(
                'INSERT INTO results (match_id, member_id, pts, rank, wg_rank_pt) VALUES (?,?,?,?,?)',
                (match_id, member_id, pts, rank, wg_pt)
            )

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'match_id': match_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/ranking')
def get_ranking():
    """
    ランキングデータ（全統計付き）をJSONで返す
    HTMLダッシュボードのDATA配列と同じ内容を生成
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM members ORDER BY member_id')
    members = cursor.fetchall()

    result = []
    for member in members:
        cursor.execute('''
        SELECT r.pts, r.rank, r.wg_rank_pt
        FROM results r
        JOIN matches mt ON r.match_id = mt.match_id
        WHERE r.member_id = ?
        ORDER BY mt.play_date, r.result_id
        ''', (member['member_id'],))

        rows = [{'pts': row['pts'], 'rank': row['rank'], 'wg_rank_pt': row['wg_rank_pt']}
                for row in cursor.fetchall()]

        stats = calculate_stats(rows)

        # 引継ぎPt = Season2最終WGランクPt ÷ 3（切り捨て）
        season2_final  = member['season2_final_wg_pt'] or 0
        inherit_pt     = season2_final // 3

        # WGランクPt合計 = 引継ぎPt + Season3 WGランクPt
        s3_wg_rank_pt    = stats['s3_wg_rank_pt'] if stats else 0
        total_wg_rank_pt = inherit_pt + s3_wg_rank_pt

        # ランク判定
        rank_info  = get_rank_info(total_wg_rank_pt)
        bar_pct    = calc_bar_pct(rank_info, total_wg_rank_pt)
        next_target = calc_next_target(
            total_wg_rank_pt,
            stats['wg_rank_pt_per_game'] if stats else 0
        )

        member_data = {
            'member_id':          member['member_id'],
            'name':               member['name'],
            'internal_key':       member['internal_key'],
            'color':              member['color'],
            # WGランクPt系
            'inherit_pt':         inherit_pt,
            's3_wg_rank_pt':      s3_wg_rank_pt,
            'total_wg_rank_pt':   total_wg_rank_pt,
            # ランク情報
            'rank_name':          rank_info['rank'],
            'rank_grade':         rank_info['grade'],
            'rank_cls':           rank_info['cls'],
            'rank_bar_color':     rank_info['bar'],
            'rank_bar_pct':       bar_pct,
            'next_target':        next_target,
        }

        if stats:
            member_data.update(stats)
        else:
            member_data.update({
                'games': 0, 'total_pts': 0, 'pts_per_game': 0.0,
                'avg_rank': None, 'top_rate': 0.0, 'ren_rate': 0.0,
                'avoid_rate': 0.0, 'last_rate': 0.0, 'plus_rate': 0.0,
                'std_dev': 0.0, 'avg_pts_1st': None, 'avg_pts_4th': None,
                'max_pts': 0, 'min_pts': 0,
                'r1': 0, 'r2': 0, 'r3': 0, 'r4': 0,
                'wg_rank_pt_per_game': 0.0, 'recent_avg_rank': None,
            })

        result.append(member_data)

    conn.close()

    # WGランクPt合計の降順でソート
    result.sort(key=lambda x: x['total_wg_rank_pt'], reverse=True)
    return jsonify(result)


@app.route('/api/trend')
def get_trend():
    """
    活動日ごとの累積Pts推移をJSONで返す
    HTMLダッシュボードのTREND配列と同じ構造
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM members ORDER BY member_id')
    members = cursor.fetchall()

    cursor.execute('SELECT DISTINCT play_date FROM matches ORDER BY play_date')
    dates = [row['play_date'] for row in cursor.fetchall()]

    # 各メンバーの累積Ptsを日付順に積み上げ
    cumulative = {m['name']: 0 for m in members}
    trend = []

    for date in dates:
        cursor.execute('''
        SELECT m.name, SUM(r.pts) as day_pts
        FROM results r
        JOIN matches mt ON r.match_id = mt.match_id
        JOIN members m  ON r.member_id = m.member_id
        WHERE mt.play_date = ?
        GROUP BY m.name
        ''', (date,))

        day_data = {row['name']: row['day_pts'] for row in cursor.fetchall()}
        for name, pts in day_data.items():
            cumulative[name] = cumulative.get(name, 0) + pts

        entry = {'date': date}
        entry.update({name: cumulative[name] for name in cumulative})
        trend.append(entry)

    conn.close()
    return jsonify(trend)


@app.route('/api/rank_board')
def get_rank_board():
    """
    WGランクボード用データをJSONで返す
    HTMLのrank_board.htmlのRANK_DATA配列と同じ内容
    """
    ranking = get_ranking().get_json()

    board = []
    for m in ranking:
        t = get_rank_info(m['total_wg_rank_pt'])
        next_t = get_next_rank(t)

        board.append({
            'name':              m['name'],
            'internal_key':      m['internal_key'],
            'color':             m['color'],
            'inherit_pt':        m['inherit_pt'],
            's3_wg_rank_pt':     m['s3_wg_rank_pt'],
            'total_wg_rank_pt':  m['total_wg_rank_pt'],
            'wg_rank_pt_per_game': m['wg_rank_pt_per_game'],
            'games':             m['games'],
            'avg_rank':          m['avg_rank'],
            'top_rate':          m['top_rate'],
            'ren_rate':          m['ren_rate'],
            'rank_name':         t['rank'],
            'rank_grade':        t['grade'],
            'rank_cls':          t['cls'],
            'rank_bar_color':    t['bar'],
            'rank_bar_pct':      calc_bar_pct(t, m['total_wg_rank_pt']),
            'need_pt_to_next':   (next_t['min'] - m['total_wg_rank_pt']) if next_t else 0,
            'next_target':       m['next_target'],
        })

    return jsonify(board)


@app.route('/api/import', methods=['POST'])
def import_excel():
    """
    Excel ファイル（Season2_戦績データ.xlsx）をアップロードしてDB に投入
    メンバー名マッピング: 土岐, 藤木, 鹿山, 河井, 松林, 岡崎, 大塚, 矢嶋, 本井
    """
    try:
        # ファイルアップロード確認
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'ファイルがアップロードされていません'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400

        # Excel を読み込み
        import pandas as pd
        df = pd.read_excel(file, sheet_name='Season2ALL', header=3)

        # メンバー名 → member_id マッピング
        member_map = {
            '土岐': 1, '藤木': 3, '鹿山': 5, '河井': 8, '松林': 4,
            '岡崎': 6, '大塚': 7, '矢嶋': 2, '本井': 9
        }

        conn = get_db_connection()
        cursor = conn.cursor()

        # match_number の開始位置を決める
        cursor.execute('SELECT MAX(match_number) FROM matches')
        result = cursor.fetchone()
        start_match_number = (result[0] or 0) + 1

        imported_count = 0
        skipped_count = 0

        # 各行を処理
        for idx, row in df.iterrows():
            if pd.isna(row['半荘']):
                continue

            play_date = row['活動日']
            if isinstance(play_date, pd.Timestamp):
                play_date_str = play_date.strftime('%Y-%m-%d')
            else:
                play_date_str = str(play_date)

            # 参加メンバーのポイントを抽出
            match_pts = []
            for member_name, member_id in member_map.items():
                pts_val = row[member_name]
                if pd.isna(pts_val) or pts_val == '-':
                    continue
                try:
                    pts = int(pts_val)
                    match_pts.append((member_id, pts))
                except (ValueError, TypeError):
                    continue

            # 参加者が4人未満の場合はスキップ
            if len(match_pts) < 4:
                skipped_count += 1
                continue

            # 試合を登録
            cursor.execute(
                'INSERT INTO matches (match_number, play_date) VALUES (?, ?)',
                (start_match_number + imported_count, play_date_str)
            )
            match_id = cursor.lastrowid

            # 順位を計算
            sorted_results = sorted(match_pts, key=lambda x: x[1], reverse=True)
            ranked = [(member_id, pts, i + 1) for i, (member_id, pts) in enumerate(sorted_results)]

            # 結果を登録
            for member_id, pts, rank in ranked:
                wg_pt = calc_wg_rank_pt(pts, rank)
                cursor.execute(
                    'INSERT INTO results (match_id, member_id, pts, rank, wg_rank_pt) VALUES (?,?,?,?,?)',
                    (match_id, member_id, pts, rank, wg_pt)
                )

            imported_count += 1

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'imported': imported_count,
            'skipped': skipped_count,
            'message': f'{imported_count}半荘を投入しました（スキップ: {skipped_count}）'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== エラーハンドラー ====================

@app.errorhandler(404)
def not_found(error):
    return "ページが見つかりません", 404

@app.errorhandler(500)
def server_error(error):
    return "サーバーエラーが発生しました", 500

# ==================== 起動 ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
