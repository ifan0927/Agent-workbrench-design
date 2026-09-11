import { expect, it } from 'vitest';
import { formatNewsDate, getNewsPosts } from './src/lib/content/news';

const valid = [
  '2026-05-15', '2026-05-15T00:00:00.000Z', '2024-02-29', '2000-02-29',
  '0001-01-01', '9999-12-31', '2026-05-15T23:59:59Z',
  '2026-05-15T00:01:02.1+14:00', '2026-05-15T23:01:02.12-14:00',
  '2026-05-15T00:00:00+08:00', '2026-05-15T23:59:59.123-07:30',
];
const invalid = [
  '', 'junk', '2026', '2026-5-15', '2026-05', '2026-05-1', '2026-00-01',
  '2026-13-01', '2026-01-00', '2026-01-32', '2026-04-31', '2026-02-29',
  '1900-02-29', '2100-02-29', '0000-01-01', '10000-01-01', '2026-05-15junk',
  ' 2026-05-15', '2026-05-15 ', '2026-05-15\n', '２０２６-05-15',
  '2026-05-15T00:00:00', '2026-05-15 00:00:00Z', '2026-05-15t00:00:00z',
  '2026-05-15T24:00:00Z', '2026-05-15T23:60:00Z', '2026-05-15T23:59:60Z',
  '2026-05-15T00:00:00.1234Z', '2026-05-15T00:00:00.Z',
  '2026-05-15T00:00:00+14:01', '2026-05-15T00:00:00-15:00',
  '2026-05-15T00:00:00+01:60', '2026-05-15T00:00:00+0800',
];
it.each(valid)('accepts valid date without timezone conversion: %s', date => {
  const [year, month, day] = date.slice(0, 10).split('-');
  expect(formatNewsDate(date)).toEqual({ year, monthDay: `${month}.${day}`, full: `${year}.${month}.${day}`, iso: `${year}-${month}-${day}` });
});
it.each(invalid)('rejects invalid date: %s', date => expect(() => formatNewsDate(date)).toThrow());
it('keeps valid editorial content loadable', () => expect(getNewsPosts().length).toBeGreaterThan(0));
