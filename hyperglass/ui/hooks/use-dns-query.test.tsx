import 'isomorphic-fetch';
import { expect, describe, it } from 'vitest';
import '@testing-library/jest-dom';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { HyperglassContext } from '~/context';
import { useDNSQuery } from './use-dns-query';

import type { Config } from '~/types';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, cacheTime: Infinity } },
});

const CloudflareWrapper = (props: React.PropsWithChildren) => {
  const config = {
    cache: { timeout: 120 },

    web: { dnsProvider: { url: 'https://cloudflare-dns.com/dns-query' } },
  } as Config;
  return (
    <QueryClientProvider client={queryClient}>
      <HyperglassContext.Provider value={config} {...props} />
    </QueryClientProvider>
  );
};

const GoogleWrapper = (props: React.PropsWithChildren) => {
  const config = {
    cache: { timeout: 120 },
    web: { dnsProvider: { url: 'https://dns.google/resolve' } },
  } as Config;
  return (
    <QueryClientProvider client={queryClient}>
      <HyperglassContext.Provider value={config} {...props} />
    </QueryClientProvider>
  );
};

describe('useDNSQuery Cloudflare', () => {
  it('Test Cloudflare DNS over HTTPS (IPv4)', async () => {
    const { result } = renderHook(() => useDNSQuery('one.one.one.one', 4), {
      wrapper: CloudflareWrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 5_000 });
    expect(result.current.data?.Answer.map(a => a.data)).toContain('1.1.1.1');
  });

  it('Test Cloudflare DNS over HTTPS (IPv6)', async () => {
    const { result } = renderHook(() => useDNSQuery('one.one.one.one', 6), {
      wrapper: CloudflareWrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 5_000 });
    expect(result.current.data?.Answer.map(a => a.data)).toContain('2606:4700:4700::1111');
  });
});

describe('useDNSQuery Google', () => {
  it('Test Google DNS over HTTPS (IPv4)', async () => {
    const { result } = renderHook(() => useDNSQuery('one.one.one.one', 4), {
      wrapper: GoogleWrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 5_000 });
    expect(result.current.data?.Answer.map(a => a.data)).toContain('1.1.1.1');
  });

  it('Test Google DNS over HTTPS (IPv6)', async () => {
    const { result } = renderHook(() => useDNSQuery('one.one.one.one', 6), {
      wrapper: GoogleWrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 5_000 });
    expect(result.current.data?.Answer.map(a => a.data)).toContain('2606:4700:4700::1111');
  });
});
