import fs from 'fs';
import { getScriptSrc } from '@chakra-ui/react';
import Document, { Html, Head, Main, NextScript } from 'next/document';
import { CustomHtml, CustomJavascript, Favicon } from '~/elements';
import { googleFontUrl } from '~/util';
import favicons from '../favicon-formats';

import type { DocumentContext, DocumentInitialProps } from 'next/document';
import type { Config } from '~/types';

/**
 * Configuration-dependent values. Production builds contain placeholders, which hyperglass
 * replaces at startup so that configuration changes don't require a new UI build. Placeholders
 * must match `hyperglass.frontend.render`.
 */
interface ConfigValues {
  config: string;
  title: string;
  description: string;
  version: string;
  fontBody: string;
  fontMono: string;
  colorModeScript: string;
  customJs: string;
  customHtml: string;
}

const COLOR_MODE_PLACEHOLDER = '__HYPERGLASS_COLOR_MODE__';

const PLACEHOLDERS: ConfigValues = {
  config: '__HYPERGLASS_CONFIG__',
  title: '__HYPERGLASS_TITLE__',
  description: '__HYPERGLASS_DESCRIPTION__',
  version: '__HYPERGLASS_VERSION__',
  fontBody: '__HYPERGLASS_FONT_BODY__',
  fontMono: '__HYPERGLASS_FONT_MONO__',
  colorModeScript: placeholderColorModeScript(),
  customJs: '__HYPERGLASS_CUSTOM_JS__',
  customHtml: '__HYPERGLASS_CUSTOM_HTML__',
};

/**
 * Chakra's color mode script only accepts valid color modes, so generate it with a known value &
 * replace that value with a placeholder.
 */
function placeholderColorModeScript(): string {
  const script = getScriptSrc({ initialColorMode: 'system' });
  const pattern = /="system",(\w+)="chakra-ui-color-mode"/;
  if (!pattern.test(script)) {
    throw new Error('Unable to create color mode script placeholder; has Chakra UI changed?');
  }
  return script.replace(pattern, `="${COLOR_MODE_PLACEHOLDER}",$1="chakra-ui-color-mode"`);
}

function readFile(path: string): string {
  return fs.existsSync(path) ? fs.readFileSync(path).toString() : '';
}

/**
 * In development mode, hyperglass writes its configuration to `hyperglass.json`, which is read on
 * each request by the Next.js development server.
 */
function developmentValues(): ConfigValues | null {
  if (!fs.existsSync('hyperglass.json')) {
    return null;
  }
  const json = readFile('hyperglass.json');
  const config = JSON.parse(json) as Config;
  return {
    config: json.replace(/</g, '\\u003c'),
    title: config.siteTitle,
    description: config.siteDescription,
    version: config.version,
    fontBody: googleFontUrl(config.web.theme.fonts.body),
    fontMono: googleFontUrl(config.web.theme.fonts.mono),
    colorModeScript: getScriptSrc({
      initialColorMode: config.web.theme.defaultColorMode ?? 'system',
    }),
    customJs: readFile('custom.js'),
    customHtml: readFile('custom.html'),
  };
}

interface DocumentExtra extends DocumentInitialProps {
  values: ConfigValues;
}

class MyDocument extends Document<DocumentExtra> {
  static async getInitialProps(ctx: DocumentContext): Promise<DocumentExtra> {
    const initialProps = await Document.getInitialProps(ctx);
    return { ...initialProps, values: developmentValues() ?? PLACEHOLDERS };
  }

  render(): JSX.Element {
    const { values } = this.props;
    return (
      <Html lang="en">
        <Head>
          <meta name="language" content="en" />
          <meta httpEquiv="Content-Type" content="text/html" />
          <meta charSet="UTF-8" />
          <title>{values.title}</title>
          <meta name="description" content={values.description} />
          <meta name="hyperglass-version" content={values.version} />
          <meta name="og:type" content="website" />
          <meta name="og:title" content={values.title} />
          <meta name="og:description" content={values.description} />
          <meta name="og:image" content="/images/opengraph.jpg" />
          <meta property="og:image:alt" content={`${values.title} - ${values.description}`} />
          <meta property="og:image:width" content="1200" />
          <meta property="og:image:height" content="630" />
          <link rel="dns-prefetch" href="//fonts.gstatic.com" />
          <link rel="dns-prefetch" href="//fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
          <link href={values.fontMono} rel="stylesheet" />
          <link href={values.fontBody} rel="stylesheet" />
          {favicons.map(favicon => (
            <Favicon key={JSON.stringify(favicon)} {...favicon} />
          ))}
          <script
            id="hyperglass-config"
            type="application/json"
            // biome-ignore lint/security/noDangerouslySetInnerHtml: configuration is JSON-encoded
            dangerouslySetInnerHTML={{ __html: values.config }}
          />
          <CustomJavascript>{values.customJs}</CustomJavascript>
        </Head>
        <body>
          <script
            id="chakra-script"
            // biome-ignore lint/security/noDangerouslySetInnerHtml: Chakra UI color mode script
            dangerouslySetInnerHTML={{ __html: values.colorModeScript }}
          />
          <Main />
          <CustomHtml>{values.customHtml}</CustomHtml>
          <NextScript />
        </body>
      </Html>
    );
  }
}

export default MyDocument;
