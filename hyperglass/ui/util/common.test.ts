import { afterEach, beforeEach, describe, expect, it, test, vi } from 'vitest';
import {
  all,
  andJoin,
  chunkArray,
  dedupObjectArray,
  entries,
  fetchWithTimeout,
  isFQDN,
  isTimeoutError,
} from './common';

test('all - all items are truthy', () => {
  // biome-ignore lint/suspicious/noSelfCompare: because this is a test, duh
  expect(all(1 === 1, true, 'one' === 'one')).toBe(true);
});

test('all - one item is not truthy', () => {
  // biome-ignore lint/suspicious/noSelfCompare: because this is a test, duh
  expect(all(1 === 1, false, 'one' === 'one')).toBe(false);
});

describe('chunkArray - chunk array into arrays of n size', () => {
  const input = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const result = chunkArray(input, 2);
  test('chunked array length', () => {
    expect(result).toHaveLength(Math.round(input.length / 2));
  });
  test.each(result)('verify chunk %#', item => {
    expect(input).toContain(item);
  });
});

describe('entries - typed Object.entries()', () => {
  const obj = { one: 1, two: 2, three: 3 };
  const result = entries(obj);
  const expectedKeys = ['one', 'two', 'three'];
  const expectedValues = [1, 2, 3];

  test.each(result)('verify k/v pair %#', (k, v) => {
    expect(expectedKeys).toContain(k);
    expect(expectedValues).toContain(v);
  });
});

describe('dedupObjectArray - deduplicate object array', () => {
  const objArray = [
    { one: 1, two: 2, three: 3 },
    { four: 4, five: 5, six: 6 },
    { seven: 7, eight: 8, nine: 9 },
    { zero: 0, one: 1, thousand: 1_000 },
  ];
  const result = dedupObjectArray(objArray, 'one');
  test('ensure duplicate object is removed', () => {
    expect(result.length).toBe(3);
  });
  test.each(result)('verify objects', obj => {
    expect(obj).toEqual(expect.not.objectContaining(objArray[3]));
  });
});

describe('andJoin - join array of strings to sentence structure', () => {
  test('basic sentence', () => {
    const result = andJoin(['Tom', 'Dick', 'Harry']);
    expect(result).toBe('Tom, Dick, & Harry');
  });
  test('one item', () => {
    const result = andJoin(['Tom']);
    expect(result).toBe('Tom');
  });
  test('mixed types', () => {
    // @ts-expect-error Test case
    const result = andJoin(['Tom', 100, 'Harry']);
    expect(result).toBe('Tom & Harry');
  });
  test('(options) wrapped', () => {
    const result = andJoin(['Tom', 'Dick', 'Harry'], { wrap: '*' });
    expect(result).toBe('*Tom*, *Dick*, & *Harry*');
  });
  test("(options) 'and' separator", () => {
    const result = andJoin(['Tom', 'Dick', 'Harry'], { separator: 'and' });
    expect(result).toBe('Tom, Dick, and Harry');
  });
  test('(options) no oxford comma', () => {
    const result = andJoin(['Tom', 'Dick', 'Harry'], { oxfordComma: false });
    expect(result).toBe('Tom, Dick & Harry');
  });
});

describe('isFQDN - determine if a string is an FQDN pattern', () => {
  it("isn't an FQDN and should be false", () => {
    expect(isFQDN('example')).toBe(false);
  });
  it('is a domain and should be true', () => {
    expect(isFQDN('example.com')).toBe(true);
  });
  it('is a simple FQDN and should be true', () => {
    expect(isFQDN('www.example.com')).toBe(true);
  });
  it('is a long FQDN and should be true', () => {
    expect(isFQDN('one.two.example.com')).toBe(true);
  });
  it('is a longer FQDN and should be true', () => {
    expect(isFQDN('one.two.three.four.five.example.com')).toBe(true);
  });
  it('is an array of FQDNs and should be true', () => {
    expect(isFQDN(['www.example.com'])).toBe(true);
  });
});

describe('fetchWithTimeout - fetch with a timeout & cancellation', () => {
  /** A `fetch` that never responds, and rejects like `fetch` when its signal is aborted. */
  const pendingFetch = vi.fn(
    (_: string, init: RequestInit = {}) =>
      new Promise<Response>((_resolve, reject) => {
        const abort = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
        if (init.signal?.aborted) {
          abort();
        }
        init.signal?.addEventListener('abort', abort);
      }),
  );

  beforeEach(() => {
    vi.useFakeTimers();
    pendingFetch.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('returns the response and clears its timer', async () => {
    const response = new Response('ok');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => response),
    );
    await expect(fetchWithTimeout('/api/query', {}, 1000)).resolves.toBe(response);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aborts the request and rejects with a TimeoutError when the timeout expires', async () => {
    vi.stubGlobal('fetch', pendingFetch);
    const result = fetchWithTimeout('/api/query', {}, 1000);
    const assertion = expect(result).rejects.toMatchObject({ name: 'TimeoutError' });
    vi.advanceTimersByTime(999);
    expect(pendingFetch.mock.calls[0][1]?.signal?.aborted).toBe(false);
    vi.advanceTimersByTime(1);
    await assertion;
    expect(pendingFetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });

  it('aborts the request when the passed signal is aborted', async () => {
    vi.stubGlobal('fetch', pendingFetch);
    const controller = new AbortController();
    const result = fetchWithTimeout('/api/query', { signal: controller.signal }, 1000);
    const assertion = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await assertion;
    expect(pendingFetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aborts the request if the passed signal is already aborted', async () => {
    vi.stubGlobal('fetch', pendingFetch);
    const controller = new AbortController();
    controller.abort();
    await expect(
      fetchWithTimeout('/api/query', { signal: controller.signal }, 1000),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(pendingFetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });

  it('uses a new signal for each request', async () => {
    vi.stubGlobal('fetch', pendingFetch);
    const first = fetchWithTimeout('/one', {}, 1000);
    const assertion = expect(first).rejects.toMatchObject({ name: 'TimeoutError' });
    vi.advanceTimersByTime(1000);
    await assertion;
    fetchWithTimeout('/two', {}, 1000).catch(() => null);
    expect(pendingFetch.mock.calls[1][1]?.signal?.aborted).toBe(false);
  });
});

describe('isTimeoutError - determine if a request timed out or was aborted', () => {
  it('is a timeout', () => {
    const error = new Error('Timeout');
    error.name = 'TimeoutError';
    expect(isTimeoutError(error)).toBe(true);
    expect(isTimeoutError(new DOMException('Aborted', 'AbortError'))).toBe(true);
  });
  it("isn't a timeout", () => {
    expect(isTimeoutError(new Error('Bad Gateway'))).toBe(false);
    expect(isTimeoutError(new TypeError('Failed to fetch'))).toBe(false);
    expect(isTimeoutError(null)).toBe(false);
    expect(isTimeoutError(undefined)).toBe(false);
  });
});
