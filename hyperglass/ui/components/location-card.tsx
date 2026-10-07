import { useId, useMemo } from 'react';
import { Flex, Avatar, chakra } from '@chakra-ui/react';
import { motionChakra } from '~/elements';
import { useColorValue, useOpposingColor } from '~/hooks';

import type { SingleOption } from '~/types';

interface LocationCardProps {
  option: SingleOption;
  isChecked: boolean;
  onChange(a: 'add' | 'remove', v: SingleOption): void;
  hasError: boolean;
}

const LocationCardWrapper = motionChakra('div', {
  baseStyle: {
    py: 4,
    px: 6,
    minW: 'xs',
    maxW: 'md',
    mx: 'auto',
    shadow: 'sm',
    rounded: 'lg',
    cursor: 'pointer',
    borderWidth: '1px',
    borderStyle: 'solid',
    _focusVisible: { outline: 'none', boxShadow: 'outline' },
  },
});

/**
 * Location selection card, which behaves like a checkbox. Its checked state is controlled by the
 * form state, so it stays in sync when the form is changed or reset elsewhere.
 */
export const LocationCard = (props: LocationCardProps): JSX.Element => {
  const { option, onChange, isChecked, hasError } = props;
  const { label } = option;
  const description = (option.data?.description as string | null | undefined) || null;
  const descriptionId = useId();

  function handleChange(): void {
    onChange(isChecked ? 'remove' : 'add', option);
  }

  function handleKeyDown(e: React.KeyboardEvent): void {
    // Toggle with Space like a checkbox, or with Enter, as the card also looks like a button.
    if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
      e.preventDefault();
      handleChange();
    }
  }

  const bg = useColorValue('white', 'blackSolid.600');
  const imageBorder = useColorValue('gray.600', 'whiteAlpha.800');
  const fg = useOpposingColor(bg);
  const checkedBorder = useColorValue('blue.400', 'blue.300');
  const errorBorder = useColorValue('red.500', 'red.300');

  const borderColor = useMemo(
    () =>
      hasError && isChecked
        ? // Highlight red when there are no overlapping query types for the locations selected.
          errorBorder
        : isChecked && !hasError
          ? // Highlight blue when any location is selected and there is no error.
            checkedBorder
          : // Otherwise, no border.
            'transparent',

    [hasError, isChecked, checkedBorder, errorBorder],
  );
  return (
    <LocationCardWrapper
      bg={bg}
      key={label}
      role="checkbox"
      tabIndex={0}
      aria-label={label}
      aria-checked={isChecked}
      aria-invalid={hasError && isChecked}
      aria-describedby={description !== null ? descriptionId : undefined}
      whileHover={{ scale: 1.05 }}
      borderColor={borderColor}
      onKeyDown={handleKeyDown}
      onClick={(e: React.MouseEvent) => {
        e.preventDefault();
        handleChange();
      }}
    >
      <>
        <Flex justifyContent="space-between" alignItems="center">
          <chakra.h2
            color={fg}
            fontWeight="bold"
            mt={{ base: 2, md: 0 }}
            fontSize={{ base: 'lg', md: 'xl' }}
          >
            {label}
          </chakra.h2>
          <Avatar
            color={fg}
            name={label}
            boxSize={12}
            rounded="full"
            borderWidth={1}
            bg="whiteAlpha.300"
            borderStyle="solid"
            borderColor={imageBorder}
            src={(option.data?.avatar as string) ?? undefined}
          />
        </Flex>

        {description !== null && (
          <chakra.p id={descriptionId} mt={2} color={fg} opacity={0.6} fontSize="sm">
            {description}
          </chakra.p>
        )}
      </>
    </LocationCardWrapper>
  );
};
