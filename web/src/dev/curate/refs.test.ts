import { describe, expect, it } from 'vitest';

import { parseRefs } from './refs';

describe('parseRefs', () => {
  it.each([
    ['a semicolon', 'way/1; node/2'],
    ['a line break', 'way/1\nnode/2'],
    ['a comma', 'way/1, node/2'],
  ])('splits references joined by %s', (_, text) => {
    expect(parseRefs(text)).toEqual(['way/1', 'node/2']);
  });

  it('takes the object of each pasted openstreetmap.org URL', () => {
    const text =
      'https://www.openstreetmap.org/way/177387348\nhttps://www.openstreetmap.org/node/5';
    expect(parseRefs(text)).toEqual(['way/177387348', 'node/5']);
  });

  it('refuses the whole text where one part names no OSM object', () => {
    expect(parseRefs('way/1; Q123')).toBeNull();
  });

  it.each(['', ' ; \n'])('refuses %j, which names nothing', (text) => {
    expect(parseRefs(text)).toBeNull();
  });
});
