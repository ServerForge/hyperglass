import { Button, Menu, MenuButton, MenuList } from '@chakra-ui/react';
import { Markdown } from '~/elements';
import { useColorValue, useBreakpointValue, useOpposingColor } from '~/hooks';

import type { MenuListProps } from '@chakra-ui/react';

interface FooterButtonProps extends Omit<MenuListProps, 'title'> {
  side: 'left' | 'right';
  title?: MenuListProps['children'];
  content: string;
}

export const FooterButton = (props: FooterButtonProps): JSX.Element => {
  const { content, title, side, ...rest } = props;

  const placement = side === 'left' ? 'top' : side === 'right' ? 'top-end' : undefined;
  const bg = useColorValue('white', 'gray.900');
  const color = useOpposingColor(bg);
  const size = useBreakpointValue({ base: 'xs', lg: 'sm' });

  return (
    <Menu placement={placement} preventOverflow isLazy>
      <MenuButton
        zIndex={2}
        as={Button}
        size={size}
        variant="ghost"
        lineHeight={0}
        aria-label={typeof title === 'string' ? title : undefined}
      >
        {title}
      </MenuButton>
      <MenuList
        px={6}
        py={4}
        bg={bg}
        // Ensure the height doesn't overtake the viewport, especially on mobile. See overflow also.
        maxH="50vh"
        color={color}
        boxShadow="2xl"
        textAlign="left"
        overflowY="auto"
        whiteSpace="normal"
        mx={{ base: 1, lg: 2 }}
        maxW={{ base: '100%', lg: '50vw' }}
        {...rest}
      >
        {/* hyperglass substitutes placeholders, so content is rendered as-is. Formatting it again
            would remove literal braces, e.g. in regular expression examples. */}
        <Markdown content={content} />
      </MenuList>
    </Menu>
  );
};
