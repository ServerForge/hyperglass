import { useQuery } from '@tanstack/react-query';
import { useConfig } from '~/context';
import { fetchWithTimeout } from '~/util';

import type {
  QueryFunction,
  QueryFunctionContext,
  QueryObserverResult,
  UseQueryOptions,
} from '@tanstack/react-query';
import type { FormQuery } from '~/types';

type LGQueryKey = [string, FormQuery];

type LGQueryOptions = Omit<
  UseQueryOptions<QueryResponse, Response | QueryResponse | Error, QueryResponse, LGQueryKey>,
  | 'queryKey'
  | 'queryFn'
  | 'cacheTime'
  | 'refetchOnWindowFocus'
  | 'refetchInterval'
  | 'refetchOnMount'
>;

/**
 * Custom hook handle submission of a query to the hyperglass backend.
 */
export function useLGQuery(
  query: FormQuery,
  options: LGQueryOptions = {} as LGQueryOptions,
): QueryObserverResult<QueryResponse> {
  const { requestTimeout, cache } = useConfig();

  const runQuery: QueryFunction<QueryResponse, LGQueryKey> = async (
    ctx: QueryFunctionContext<LGQueryKey>,
  ): Promise<QueryResponse> => {
    const [url, data] = ctx.queryKey;
    const { queryLocation, queryTarget, queryType } = data;
    const res = await fetchWithTimeout(
      url,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          queryLocation,
          queryTarget,
          queryType,
        }),
        mode: 'cors',
        // Abort the request when the query is cancelled, e.g. when the form is reset.
        signal: ctx.signal,
      },
      requestTimeout * 1000,
    );
    try {
      const data = await res.json();
      return data;
    } catch (err) {
      // e.g. an HTML error page from a reverse proxy. `statusText` is empty over HTTP/2.
      throw new Error(`${res.status} ${res.statusText}`.trim());
    }
  };

  return useQuery<QueryResponse, Response | QueryResponse | Error, QueryResponse, LGQueryKey>({
    queryKey: ['/api/query', query],
    queryFn: runQuery,
    // Don't refetch when window refocuses.
    refetchOnWindowFocus: false,
    // Don't automatically refetch query data (queries should be on-off).
    refetchInterval: false,
    // Don't refetch on component remount.
    refetchOnMount: false,
    // Show failures instead of retrying them, as each attempt runs commands on the device.
    retry: false,
    ...options,
  });
}
