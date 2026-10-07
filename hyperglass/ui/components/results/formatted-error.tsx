import { chakra } from '@chakra-ui/react';

interface FormattedErrorProps {
  keywords: string[];
  message: string;
}

type FormatError = string | JSX.Element;

/**
 * Escape characters with special meaning in regular expressions, so a value is matched literally.
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Build a pattern matching any keyword. Keywords often contain user input (e.g. the query target),
 * so they're matched literally.
 */
function keywordPattern(keywords: string[]): RegExp | null {
  const literals = keywords.filter(kw => kw !== '').map(kw => escapeRegExp(String(kw)));
  if (literals.length === 0) {
    return null;
  }
  try {
    return new RegExp(`(${literals.join('|')})`, 'gi');
  } catch (err) {
    return null;
  }
}

/**
 * Split text into parts, with each keyword match in bold.
 */
export function formatError(text: string, keywords: string[]): FormatError[] | FormatError {
  const pattern = keywordPattern(keywords);
  if (pattern === null || typeof text !== 'string') {
    return text;
  }
  // Splitting on a pattern with a single capture group places matches at odd indices.
  return text
    .split(pattern)
    .map((part, i) => (i % 2 === 1 ? <strong key={`${i}${part}`}>{part}</strong> : part));
}

export const FormattedError = (props: FormattedErrorProps): JSX.Element => {
  const { keywords, message } = props;
  const things = formatError(message, keywords);
  return (
    <chakra.span fontWeight={keywords.length === 0 ? 'bold' : undefined}>
      {keywords.length !== 0 ? things : message}
    </chakra.span>
  );
};
