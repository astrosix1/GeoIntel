// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { describeScope } from '../src/lib/scopeWhy.ts';

describe('describeScope', () => {
  it('explains a global verdict with the global terms that decided it', () => {
    const why = describeScope('global', { rule: 'global terms', global: ['UN', 'sanctions'], local: ['mayor'] });
    assert.equal(why?.summary, 'The headline matches international topics.');
    assert.deepEqual(why?.terms, ['UN', 'sanctions']);
  });

  it('explains a local verdict with the local terms', () => {
    const why = describeScope('local', { rule: 'local terms and a specific place', global: [], local: ['police', 'arrested'] });
    assert.match(why?.summary ?? '', /precise to a town or city/);
    assert.deepEqual(why?.terms, ['police', 'arrested']);
  });

  it('says so when nothing matched', () => {
    const why = describeScope('global', { rule: 'no match, default', global: [], local: [] });
    assert.match(why?.summary ?? '', /No topic word matched/);
    assert.deepEqual(why?.terms, []);
  });

  it('has nothing to say for an event not judged yet or an unknown rule', () => {
    assert.equal(describeScope('global', null), null);
    assert.equal(describeScope('global', undefined), null);
    assert.equal(describeScope('global', { rule: 'something new', global: [], local: [] }), null);
    assert.equal(describeScope('global', { rule: 5 } as never), null);
  });

  it('ignores malformed term lists', () => {
    const why = describeScope('local', { rule: 'local terms', global: [], local: 'x' as never });
    assert.deepEqual(why?.terms, []);
  });
});
