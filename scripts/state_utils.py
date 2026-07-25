"""Shared state calculation — used by render_views, serve.py, export_dashboard."""
import sqlite3, json

def get_char_summary(db_path):
    """Return list of {name,type,pools,loc,status} for all characters."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    chars = []
    for ch in conn.execute(
        "SELECT char_name,char_type,base_stats FROM char_base ORDER BY CASE char_type WHEN 'pc' THEN 0 END, char_name"
    ):
        base = json.loads(ch['base_stats'])
        totals = dict(base)
        for d in conn.execute(
            "SELECT deltas FROM char_state_log WHERE char_name=? ORDER BY seq",
            (ch['char_name'],)
        ):
            for k, v in json.loads(d['deltas']).items():
                totals[k] = totals.get(k, 0) + v
        last = conn.execute(
            "SELECT loc_new,status_new FROM char_state_log WHERE char_name=? AND (loc_new IS NOT NULL OR status_new IS NOT NULL) ORDER BY seq DESC LIMIT 1",
            (ch['char_name'],)
        ).fetchone()
        pools = {}
        for k in sorted(base.keys()):
            pools[k] = {"cur": totals.get(k, '?'), "max": base[k]}
        chars.append({
            "name": ch['char_name'],
            "type": ch['char_type'],
            "pools": pools,
            "loc": last['loc_new'] if last and last['loc_new'] else '-',
            "status": last['status_new'] if last and last['status_new'] else '-',
        })
    conn.close()
    return chars
