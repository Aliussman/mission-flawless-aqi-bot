from datetime import datetime, timezone

def make_status_record(node_id, online, last_seen=None):
    return {
        "node_id": node_id,
        "online": bool(online),
        "last_seen": last_seen,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
