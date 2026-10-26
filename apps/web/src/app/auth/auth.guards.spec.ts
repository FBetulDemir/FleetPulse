import { safeReturnUrl } from './auth.guards';

describe('safeReturnUrl', () => {
  it.each([
    ['/vessels/1?tab=history', '/vessels/1?tab=history'],
    [null, '/'],
    ['', '/'],
    ['https://evil.example', '/'],
    ['//evil.example/path', '/'],
    ['javascript:alert(1)', '/'],
  ])('turns %s into %s', (input, expected) => {
    expect(safeReturnUrl(input)).toBe(expected);
  });
});
