import { useEffect, useState } from 'react';
import Head from 'next/head';
import { useConfig } from '~/context';

/**
 * Client-side metadata. Configuration-dependent metadata (title, description, etc.) is rendered by
 * `_document`, so it's present in the HTML for crawlers & link previews. The title must also be
 * rendered here, as Next.js otherwise clears it on the client.
 */
export const Meta = (): JSX.Element => {
  const { siteTitle } = useConfig();
  const [location, setLocation] = useState('/');

  useEffect(() => {
    if (typeof window !== 'undefined' && location === '/') {
      setLocation(window.location.href);
    }
  }, [location]);

  return (
    <Head>
      <title key="title">{siteTitle}</title>
      <meta name="url" content={location} />
      <meta name="og:url" content={location} />
      <meta
        name="viewport"
        content="width=device-width, initial-scale=1, user-scalable=no, maximum-scale=1.0, minimum-scale=1.0"
      />
    </Head>
  );
};
