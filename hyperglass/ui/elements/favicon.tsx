import type { Favicon as FaviconProps } from '~/types';

/**
 * Render a `<link/>` element to reference a server-side favicon.
 */
export const Favicon = (props: FaviconProps): JSX.Element => {
  const { image_format, dimensions, prefix, rel } = props;
  const [w, h] = dimensions;
  // ICO files contain multiple sizes, so their file name has no dimensions.
  const file = image_format === 'ico' ? `${prefix}.ico` : `${prefix}-${w}x${h}.${image_format}`;
  const src = `/images/favicons/${file}`;
  return <link rel={rel ?? ''} href={src} type={`image/${image_format}`} />;
};
