CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT,
    youtube_id TEXT UNIQUE,
    local_path TEXT,
    source TEXT NOT NULL CHECK(source IN ('local','youtube')),
    track_type TEXT NOT NULL DEFAULT 'karaoke' CHECK(track_type IN ('karaoke','dj')),
    duration_sec INTEGER,
    start_offset_sec REAL DEFAULT 0,
    play_count INTEGER DEFAULT 0,
    last_played DATETIME,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mode TEXT DEFAULT 'karaoke',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER REFERENCES playlists(id),
    track_id INTEGER REFERENCES tracks(id),
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    mode TEXT DEFAULT 'karaoke',
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME
);
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    track_id INTEGER REFERENCES tracks(id),
    singer_name TEXT,
    position INTEGER NOT NULL,
    status TEXT DEFAULT 'waiting' CHECK(status IN ('waiting','playing','done','skipped')),
    pitch_offset INTEGER DEFAULT 0,
    tempo_ratio REAL DEFAULT 1.0,
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS download_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER REFERENCES tracks(id),
    trigger TEXT,
    status TEXT DEFAULT 'pending',
    downloaded_at DATETIME
);
