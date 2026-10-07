import { expect, describe, it } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom';
import { FormattedError, formatError } from './formatted-error';

const strongText = (container: HTMLElement): (string | null)[] =>
  [...container.querySelectorAll('strong')].map(s => s.textContent);

describe('FormattedError', () => {
  // Keywords often contain the user's query target, which may be an invalid regular expression.
  it.each(['1.1.1.0/24(', '[', '65000:1\\', '.*', '(?<'])('highlights keyword %j', keyword => {
    const message = `Target ${keyword} is not valid`;
    const { container } = render(<FormattedError message={message} keywords={[keyword]} />);
    expect(container.textContent).toBe(message);
    expect(strongText(container)).toEqual([keyword]);
  });

  it('matches keywords literally', () => {
    const { container } = render(
      <FormattedError message="Target 1.1.1.0 is not 1x1y1z0" keywords={['1.1.1.0']} />,
    );
    expect(strongText(container)).toEqual(['1.1.1.0']);
  });

  it('highlights every keyword, ignoring case', () => {
    const { container } = render(
      <FormattedError
        message="Device R1 can't query 192.0.2.0/24 or r1"
        keywords={['r1', '192.0.2.0/24']}
      />,
    );
    expect(strongText(container)).toEqual(['R1', '192.0.2.0/24', 'r1']);
  });

  it('renders the message in bold without keywords', () => {
    const { container } = render(<FormattedError message="Something went wrong" keywords={[]} />);
    expect(container.textContent).toBe('Something went wrong');
    expect(strongText(container)).toEqual([]);
  });

  it("doesn't throw for a missing message", () => {
    expect(formatError(undefined as unknown as string, ['x'])).toBeUndefined();
  });
});
