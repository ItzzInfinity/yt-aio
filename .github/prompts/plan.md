# Plan: Fix Timeout Errors in Playlist/Channel Fetching (1.8.1)

## TL;DR

**Problem**: Fetching videos from large channels/playlists (100+ videos) times out because the current implementation fetches the entire playlist as a single synchronous JSON dump via `--flat-playlist --dump-single-json` (no timeout enforced).

**Solution**: Implement chunked, progressive fetching with:
- **Chunked extraction** — Fetch playlists in 100-video batches using `--playlist-start` / `--playlist-end`
- **Progressive UI updates** — Display results as each chunk loads (stream to UI with "Batch 3/12" counter)
- **120-second timeout per chunk** — Prevents individual timeouts from blocking entire operation
- **Resume-on-failure** — If a chunk times out, retry; if persistent, return partial results (if >80% complete)
- **Detailed logging** — New `chunk_fetch_history` database table tracks each batch

---

## Implementation Plan

### **Phase 1: Infrastructure & Architecture** (Parallel discovery)

| Step | Task | Details |
|------|------|---------|
| 1.1 | Create `ChunkedPlaylistFetcher` class | New class in `video_info_extractor.py` with methods: `fetch_chunk()`, `estimate_playlist_size()`, `stream_chunks()` |
| 1.2 | Extend `config.json` | Add: `chunk_size: 100`, `chunk_timeout: 120`, `enable_progressive_fetching: true`, `max_chunk_retries: 2` |
| 1.3 | Update `ConfigManager` | Validate new chunking keys; provide sensible defaults |
| 1.4 | Create `ProgressTracker` helper | New class in `shared.py` for UI progress updates |

### **Phase 2: Update Fetching Logic** (Core implementation)

| Step | Task | Details |
|------|------|---------|
| 2.1 | Refactor `list_videos()` | Add decision point: ≤100 videos → single request (backward compatible); >100 → chunked approach. Add `on_progress` callback |
| 2.2 | Implement chunk extraction | Construct `--playlist-start N --playlist-end M --flat-playlist --dump-single-json` with 120s timeout per chunk |
| 2.3 | Add resume/retry logic | Track `last_successful_chunk_index`; retry failed chunks up to 2x; return partial results if >80% complete |
| 2.4 | Stream metadata fetching | Start parallel metadata resolution as chunks arrive (don't wait for all entries) |

### **Phase 3: UI Integration** (User feedback)

| Step | Task | Details |
|------|------|---------|
| 3.1 | Update `TaskThread.run()` | Pass progress callback to `list_videos()` for "load" action |
| 3.2 | Add progress bar + counter | Display: "Loaded 245/1200 videos (Batch 3/12)" below video list |
| 3.3 | Add cancellation support | Respect `CancellationToken` to allow user stop mid-fetch; retain partial results |
| 3.4 | Real-time log output | Show batch completion messages in log textbox |

### **Phase 4: Logging & Monitoring** (Observability)

| Step | Task | Details |
|------|------|---------|
| 4.1 | Add `chunk_fetch_history` table | Log every chunk attempt: start_idx, end_idx, duration, result_count, status, error_message |
| 4.2 | Update error logging | Capture chunk metadata in error records (chunk index, entries fetched so far, timeout) |
| 4.3 | Add detailed console logging | Log chunk start/end with timing; log cache hits/misses; log retry attempts |

### **Phase 5: Config & Version Updates**

| Step | Task | Details |
|------|------|---------|
| 5.1 | Update `config.json` | Finalize chunking defaults (from Phase 1.2) |
| 5.2 | Update docs | Add to README.md & PROGRESS_LOG.md; increment version (e.g., v1.x.x → v1.y.0); log with timestamp |
| 5.3 | Database schema migration | Add `chunk_fetch_history` table on first run if missing |

---

## Relevant Files

| File | Changes | Specifics |
|------|---------|-----------|
| [yt_aio/application/utils/video_info_extractor.py](yt_aio/application/utils/video_info_extractor.py) | **Major** | Add `ChunkedPlaylistFetcher` class; refactor `list_videos()` to use chunking for >100 videos |
| [yt_aio/application/utils/shared.py](yt_aio/application/utils/shared.py) | **Minor** | Add `ProgressTracker` helper class |
| [yt_aio/application/ui/main_window.py](yt_aio/application/ui/main_window.py#L125) | **Moderate** | Update `TaskThread.run()` to handle progress callbacks; add progress bar widget |
| [yt_aio/application/utils/config_manager.py](yt_aio/application/utils/config_manager.py) | **Minor** | Validate new chunking config keys |
| [yt_aio/application/config/config.json](yt_aio/application/config/config.json) | **Minor** | Add chunking parameters |
| [yt_aio/application/db/database_manager.py](yt_aio/application/db/database_manager.py) | **Moderate** | Add `chunk_fetch_history` table schema; update error logging |
| [README.md](README.md) & [PROGRESS_LOG.md](PROGRESS_LOG.md) | **Minor** | Document changes; update version number |

---

## Verification Strategy

**Automated Tests:**
1. Verify `--playlist-start` / `--playlist-end` parameters constructed correctly
2. Verify timeout enforced per chunk; process killed on timeout
3. Verify resume from last successful chunk on retry
4. Verify `on_progress` callback called with correct counts
5. Verify small playlists (≤100 videos) still use single-request path
6. Verify config validation for new keys

**Manual Integration Tests:**
1. **Real 100–300 video channel**: Fetch without timeout; verify chunk history logged; check progress updates in UI
2. **Very large 1000+ video playlist**: Verify chunking works; progress bar updates correctly; partial results on timeout
3. **User cancellation**: Mid-fetch cancel; verify partial results retained; UI responsive
4. **Network interruption**: Simulate timeout; verify resume capability; error logged correctly
5. **Regression**: Existing small playlist/channel fetch still works

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **Chunk size: 100 videos** | Aggressive chunking; avoids timeout for 99% of cases; configurable via config.json |
| **Timeout: 120 seconds per chunk** | Moderate baseline (accounts for YouTube rate limiting); configurable per user needs |
| **Resume strategy** | Retry same chunk up to 2x; if persistent failure, continue to next chunk; return partial results if >80% complete |
| **Backward compatibility** | Single-request path preserved for ≤100 video playlists (no behavior change for small sources) |
| **Progressive UI updates** | Show batch counter + estimated total ("Batch 3/12") to reassure user that progress is being made |
| **No breaking API changes** | New config parameters optional with sensible defaults; existing code continues to work |

---

## Further Considerations

1. **YouTube bot challenges**: Existing cookie-based auth fallback already in place; may need testing with chunked approach
2. **Metadata priority ordering**: Currently fetches metadata in parallel for all entries; future optimization could prioritize frequently-viewed videos first (out of scope for 1.8.1)
3. **Lightweight size estimation**: For channels with 10k+ videos, even size estimation might timeout; may need separate lightweight query in future
4. **Database migration framework**: No formal migration system exists; manual table creation on first run acceptable for now
5. **Download workflow progress**: Downloads already have parallel execution; no callback integration needed for phase 1

---

## Implementation Order
1. Phase 1 (Infrastructure) — Days 1-2
2. Phase 2 (Fetching Logic) — Days 2-3
3. Phase 3 (UI) — Day 3-4
4. Phase 4 (Logging) — Day 4 (can overlap with Phase 3)
5. Phase 5 (Config/Version) — Day 4-5
6. Testing — Day 5-6
