// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { isTopic, topicsOf, typeLabel, TOPICS, TYPES_COVERED_BY_TOPICS } from '../src/lib/topics.ts';

const of = (title: string, type = 'conflict') => topicsOf({ title, type });

describe('shootings', () => {
  it('finds shootings in headlines', () => {
    for (const title of [
      'Gunman opens fire at a school in Ohio',
      'Two killed in shooting outside a bar',
      'Police shoot man after chase',
      'Man shot dead in Karachi',
      'Shooter at large after mall attack',
      'Residents report gunfire near the border',
    ]) assert.ok(of(title).includes('shooting'), title);
  });

  it('does not call a missile or drone shoot-down a shooting', () => {
    for (const title of ['Air defences shoot down drone over Kyiv', 'Jet shot down near the border', 'Navy shoots down missile']) {
      assert.ok(!of(title).includes('shooting'), title);
    }
  });

  it('ignores figures of speech', () => {
    assert.deepEqual(of('Singer shot to fame overnight'), []);
  });
});

describe('protests', () => {
  it('finds protests from the headline', () => {
    assert.ok(of('Thousands protest against the new law').includes('protest'));
    assert.ok(of('Riot police clash with demonstrators').includes('protest'));
    assert.ok(of('Workers rally against pay cuts').includes('protest'));
    // The feed's civil_unrest type alone is too noisy to count.
    assert.ok(!of('Driver airlifted after crash', 'civil_unrest').includes('protest'));
  });

  it('does not treat a market rally or a military strike as a protest', () => {
    assert.ok(!of('Stocks rally as oil falls').includes('protest'));
    assert.ok(!of('Air strike hits a depot').includes('protest'));
  });
});

describe('elections', () => {
  it('finds election news and the feed type election', () => {
    assert.ok(of('Voters head to the polls in a runoff').includes('election'));
    assert.ok(of('Opposition disputes election result').includes('election'));
    assert.ok(of('Referendum set for March').includes('election'));
    assert.ok(of('Parliament meets', 'election').includes('election'));
  });

  it('does not count every vote', () => {
    assert.ok(!of('Security Council votes on sanctions').includes('election'));
  });
});

describe('crime', () => {
  it('finds crime reporting', () => {
    for (const title of ['Man arrested over robbery', 'Fraud ring charged with theft', 'Police said the stabbing was random', 'Smuggling gang sentenced']) {
      assert.ok(of(title).includes('crime'), title);
    }
  });

  it('is empty for ordinary diplomacy', () => {
    assert.deepEqual(of('Ministers meet to discuss trade', 'diplomatic'), []);
  });
});

describe('overlap and helpers', () => {
  it('lets an event belong to several topics', () => {
    const topics = of('Gunman opens fire at protest, two arrested');
    assert.deepEqual(topics.sort(), ['crime', 'protest', 'shooting']);
  });

  it('copes with missing fields', () => {
    assert.deepEqual(topicsOf({}), []);
    assert.deepEqual(topicsOf({ title: null, type: null }), []);
  });

  it('names the topics in a fixed order, and recognises them', () => {
    assert.deepEqual(TOPICS.map((t) => t.label), ['Shootings', 'Protests', 'Elections', 'Crime']);
    assert.ok(isTopic('crime') && !isTopic('diplomatic') && !isTopic(null));
  });

  it('hides the feed types that a topic already covers, and prettifies the rest', () => {
    assert.ok(TYPES_COVERED_BY_TOPICS.has('election') && !TYPES_COVERED_BY_TOPICS.has('civil_unrest'));
    assert.equal(typeLabel('civil_unrest'), 'Civil unrest');
    assert.equal(typeLabel('diplomatic'), 'Diplomatic');
  });
});
