# Fork compatibility

This fork merges `getzep/graphiti` main through
`9b8a4630092084734b080f2e6f409c2c23bdcc3a` (Graphiti 0.31.2).

The fork retains these extensions:

- `Graphiti.add_episode(new_episode_uuid=...)` creates an episode with a caller
  supplied ID. Upstream's `uuid=...` loads an existing episode;
  `existing_episode_uuid=...` is an explicit alias for that lookup.
  Creation and existing-episode IDs cannot be combined.
- `RawEpisode` accepts the same creation and lookup IDs. Omitting an ID preserves
  upstream's generated-ID behavior. Explicit creation IDs also work with
  concurrent ingestion.
- `context_prompt` on single and bulk ingestion prefixes custom extraction
  instructions, separated by a blank line. Upstream positional arguments retain
  their original order; fork extensions are keyword-only.
- FalkorDB relationship writes retain explicit property assignments, and the
  fallback transaction path writes episode nodes individually to avoid complex
  `UNWIND` parameter payloads.
- The search interface uses Pydantic's `ConfigDict` configuration.

Upstream's shared fulltext builder supersedes the fork's older empty-query fix:
empty and stopword-only input produces no search query. The fork does not retain
the removed Kuzu driver.
