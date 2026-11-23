"""Keep the fork's creation IDs and context compatible with upstream ingestion."""

from datetime import datetime, timezone

import pytest

from graphiti_core import graphiti as graphiti_module
from graphiti_core.driver.driver import GraphProvider
from graphiti_core.ingestion import phases
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.bulk_utils import RawEpisode
from tests.ingestion.ingestion_fixtures import GROUP, T0, Harness
from tests.test_graphiti_configurable_prompts import _make_graphiti


class ExtractionReached(Exception):
    """Stop at the extraction boundary before any model or graph I/O."""


@pytest.mark.parametrize('bulk', [False, True])
async def test_creation_id_and_context_reach_extraction(monkeypatch, bulk):
    graphiti = _make_graphiti()
    graphiti.driver.provider = GraphProvider.FALKORDB
    graphiti.driver._database = 'tenant'
    observed = []

    async def no_write(*args, **kwargs):
        return None

    async def previous_episodes(*args, **kwargs):
        return []

    async def episode_context(driver, episodes, **kwargs):
        return [(episode, []) for episode in episodes]

    async def extract(clients, episode, previous, entity_types, excluded, instructions):
        observed.append((episode.uuid, instructions, clients.driver))
        raise ExtractionReached

    async def extract_bulk(clients, contexts, *args, custom_extraction_instructions, **kwargs):
        observed.extend(
            (episode.uuid, custom_extraction_instructions, clients.driver)
            for episode, _ in contexts
        )
        raise ExtractionReached

    monkeypatch.setattr(graphiti, 'retrieve_episodes', previous_episodes)
    monkeypatch.setattr(graphiti_module, 'add_nodes_and_edges_bulk', no_write)
    monkeypatch.setattr(graphiti_module, 'retrieve_previous_episodes_bulk', episode_context)
    monkeypatch.setattr(graphiti_module, 'extract_nodes', extract)
    monkeypatch.setattr(graphiti_module, 'extract_nodes_and_edges_bulk', extract_bulk)
    fields = dict(
        name='meeting',
        source_description='transcript',
        reference_time=datetime(2026, 11, 23, tzinfo=timezone.utc),
        source=EpisodeType.text,
        new_episode_uuid='canonical-source-id',
    )

    with pytest.raises(ExtractionReached):
        if bulk:
            await graphiti.add_episode_bulk(
                [RawEpisode.model_validate(dict(content='Alice joined Acme', **fields))],
                group_id='tenant',
                context_prompt='  Company context  ',
                custom_extraction_instructions='  Extract decisions  ',
            )
        else:
            await graphiti.add_episode(
                episode_body='Alice joined Acme',
                group_id='tenant',
                context_prompt='  Company context  ',
                custom_extraction_instructions='  Extract decisions  ',
                **fields,
            )

    assert observed == [
        ('canonical-source-id', 'Company context\n\nExtract decisions', graphiti.driver)
    ]


@pytest.mark.parametrize(
    'id_fields', [{}, {'uuid': 'stored-id'}, {'existing_episode_uuid': 'stored-id'}]
)
def test_raw_episode_accepts_upstream_and_fork_existing_ids(id_fields):
    episode = RawEpisode.model_validate(
        dict(
            name='meeting',
            content='Alice joined Acme',
            source_description='transcript',
            reference_time='2026-11-23T00:00:00Z',
            source='text',
            **id_fields,
        )
    )
    assert episode.uuid == ('stored-id' if id_fields else None)
    assert RawEpisode.model_validate(episode.model_dump()) == episode


async def test_creation_rejects_ambiguous_ids():
    graphiti = _make_graphiti()
    with pytest.raises(ValueError, match='cannot be provided at the same time'):
        await graphiti.create_episodic_node(
            new_episode_uuid='new-id', existing_episode_uuid='stored-id'
        )


@pytest.mark.parametrize('bulk', [False, True])
async def test_concurrent_admission_retains_creation_ids(monkeypatch, bulk):
    h = Harness(monkeypatch)

    async def episode_context(driver, episodes, **kwargs):
        return [(episode, []) for episode in episodes]

    monkeypatch.setattr(phases, 'retrieve_previous_episodes_bulk', episode_context)
    fields = dict(
        name='meeting',
        source_description='transcript',
        reference_time=T0,
        source=EpisodeType.text,
        new_episode_uuid='canonical-source-id',
    )
    if bulk:
        unit = await phases.admit_bulk(
            h.graphiti,
            h.store,
            h.config,
            unit_id='unit',
            group_id=GROUP,
            bulk_episodes=[RawEpisode.model_validate(dict(content='Alice joined Acme', **fields))],
        )
    else:
        unit = await phases.admit_episode(
            h.graphiti,
            h.store,
            h.config,
            unit_id='unit',
            group_id=GROUP,
            episode_body='Alice joined Acme',
            **fields,
        )

    assert list(h.graph.episodes) == ['canonical-source-id']
    assert unit.episodes[0].uuid == 'canonical-source-id'
    await h.store.close()
