import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { AppProps } from 'next/app';
import { Layout, Meta } from '~/components';
import { HyperglassProvider } from '~/context';
import type { Config } from '~/types';

const queryClient = new QueryClient();

/**
 * Read the configuration embedded in the page by `_document`. Configuration is read at runtime
 * rather than at build time, so configuration changes don't require a new UI build.
 */
function readConfig(): Config {
  const element = document.getElementById('hyperglass-config');
  return JSON.parse(element?.textContent ?? '{}') as Config;
}

const App = (props: AppProps): JSX.Element | null => {
  const { Component, pageProps } = props;
  // Configuration is only available in the browser, so render nothing until it's been read. This
  // also ensures the first client render matches the pre-rendered (configuration-less) HTML.
  const [config, setConfig] = useState<Config | null>(null);
  useEffect(() => setConfig(readConfig()), []);

  if (config === null) {
    return null;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <HyperglassProvider config={config}>
        <Meta />
        <Layout>
          <Component {...pageProps} />
        </Layout>
      </HyperglassProvider>
    </QueryClientProvider>
  );
};

export default App;
