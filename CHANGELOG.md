# Changelog

## 0.1.2 - 2026-08-16

### Added

- List every concrete item MDBList could not match directly below the sync
  status, including title, TMDB/TVDB ID, and IMDb ID when available.
- Identify exact items after a partial `not_found` response by performing one
  conditional, paginated list read.

### Optimized

- Do not perform an extra verification request when MDBList accepts every
  item, rejects none, or rejects all attempted items. When all attempted items
  are rejected, Listarr already knows their identities from the request.
- Never use one lookup request per title. Partial failures require at most one
  additional list traversal (one request per 1000 list items).

## 0.1.1 - 2026-08-16

### Fixed

- Resolve named static lists from the concrete `/lists/user` response instead
  of the merged `unified=true` representation, which can omit the writable
  list ID.
- Match configured list names case-insensitively.
- Raise an actionable error when MDBList does not return a usable static-list
  ID.
- Accept both documented object metadata and the single-item metadata list
  observed from `GET /lists/{id}` in production.
- Report actual `added`, `removed`, `existing`, and `not_found` counts returned
  by MDBList, aggregated across all request batches.
- Distinguish dry-run plans from completed API mutations in CLI output.

## 0.1.0 - 2026-08-16

- Initial public release with Radarr and Sonarr synchronization to private
  MDBList lists.
